import asyncio
import random
import os
from loguru import logger
from src.core.advanced_account_manager import AdvancedAccountManager, AccountConfig
from src.core.data_manager import DataManager
from src.core.content_engine import ContentEngine
# RUTHLESS AUDIT FIX: Import ListingGenerator
from src.core.generator import ListingGenerator
from src.marketplace.poster import start_new_listing, fill_listing_details, fill_advanced_details, publish_listing

# Configuration
STORAGE_DIR = "user_data"
# LISTINGS_CSV = "listings.csv" # Deprecated in favor of Generation
HISTORY_FILE = "posting_history.json"
MAX_CONCURRENT_ACCOUNTS = 5
DRY_RUN = True

async def posting_task(context, listing, content_engine):
    """
    The Unit of Work: One Account posts One Listing.
    """
    page = await context.new_page()
    
    # 1. Verification: Check if logged in
    await page.goto("https://facebook.com")
    try:
        if await page.locator('div[role="navigation"]').is_visible():
            logger.info("Session verified. Logged in.")
        else:
             # Try a second check
             if await page.locator('input[name="email"]').is_visible():
                 raise RuntimeError("Session Expired: Redirected to Login Page.")
    except Exception as e:
        logger.warning(f"Login verification failed: {e}")
        # RUTHLESS AUDIT FIX: Re-throw to trigger auto-login logic in caller
        raise RuntimeError("Session Check Failed")

    # 2. Content Prep (Images)
    # The listing comes with metadata, but we need images.
    # If images list is empty, we GENERATE them.
    if not listing.images:
        logger.info(f"Generating images for '{listing.title}'...")
        prompt = f"{listing.title}, {listing.description[:100]}"
        # Generate 3 images
        listing.images = await content_engine.fetch_ai_images(prompt, count=3)
    
    if not listing.images:
        raise ValueError("Image generation failed. Cannot post.")

    # 3. Content Prep (Text Hygiene) - Optional if we trust the Generator
    # But running it through ContentEngine ensures tone matching.
    listing_dict = listing.model_dump()
    ai_content = await content_engine.generate_listing_content(listing_dict)
    
    # Update Listing
    clean_listing = listing.model_copy(update={
        "title": ai_content.get("title", listing.title),
        "description": ai_content.get("description", listing.description),
        "price": int(ai_content.get("price_logic", listing.price)),
        "images": listing.images
    })

    # 4. Execute Posting Flow
    await start_new_listing(page, clean_listing)
    await fill_listing_details(page, clean_listing)
    await fill_advanced_details(page, clean_listing)
    await publish_listing(page, dry_run=DRY_RUN)
    
    logger.success(f"Successfully posted: {clean_listing.title}")

async def main():
    logger.info("Starting UNIFIED AUTONOMOUS RUNNER (Production Mode)...")
    
    # 1. Initialize Components
    # We pass None for CSV since we use Generator
    data_manager = DataManager("dummy.csv", HISTORY_FILE) 
    content_engine = ContentEngine(processed_dir="processed_images")
    listing_generator = ListingGenerator(content_engine)
    
    # 2. Setup Accounts (Load from config/accounts.json)
    accounts_path = os.path.abspath("config/accounts.json")
    accounts = []
    
    if os.path.exists(accounts_path):
        try:
            import json
            with open(accounts_path, 'r') as f:
                raw_data = json.load(f)
                for acc in raw_data:
                    # Filter out example placeholders if needed or just load
                    if "proxy_address" in str(acc.get("proxy_url", "")):
                         logger.warning(f"Skipping template account {acc['account_id']} with invalid proxy.")
                         continue
                    accounts.append(AccountConfig(**acc))
            logger.info(f"Loaded {len(accounts)} accounts from {accounts_path}")
        except Exception as e:
            logger.error(f"Failed to load accounts config: {e}")

    # Fallback for demo if no valid accounts loaded
    if not accounts:
        # RUTHLESS AUDIT FIX: No more mock accounts.
        # We raise error if configuration is empty.
        logger.error("No valid accounts found in config/accounts.json. Please configure accounts.")
        logger.error("Format: [{ 'account_id': '...', 'proxy_url': '...', 'city': '...' }]")
        return
    
    manager = AdvancedAccountManager(accounts, max_concurrency=MAX_CONCURRENT_ACCOUNTS, storage_dir=STORAGE_DIR)
    
    try:
        await manager.start()
        
        while True:
            logger.info("--- Starting Scheduler Loop ---")
            
            # 3. Assign Work
            # Instead of loading CSV, we generate fresh listings for each account's city
            tasks = []
            
            for account in accounts:
                # RUTHLESS AUDIT FIX: Check Daily Limits
                if not data_manager.check_daily_limit(account.account_id, account.max_posts_per_day):
                    logger.info(f"[{account.account_id}] Daily post limit reached. Skipping.")
                    continue

                # Check if we have pending work or need to generate
                # For simplicity in this loop: We generate 1 fresh listing per account per cycle
                # In prod, you'd check a database queue.
                
                logger.info(f"Generating work for {account.account_id} ({account.city})...")
                new_listings_data = await listing_generator.generate_listings(account.city, count=1)
                
                if new_listings_data:
                    # Convert dict to model
                    from src.marketplace.models import RentalListing
                    target_listing = RentalListing(**new_listings_data[0])
                    
                    # Define the task wrapper
                    async def task_wrapper(ctx, acc_id=account.account_id, lst=target_listing):
                        # Attempt to post
                        try:
                            await posting_task(ctx, lst, content_engine)
                            data_manager.mark_as_posted(lst, account_id=acc_id)
                        except RuntimeError as re:
                            if "Session Check Failed" in str(re):
                                logger.warning(f"[{acc_id}] Session dead. Attempting Auto-Login...")
                                # Call login on the manager
                                success = await manager.perform_login(ctx, acc_id)
                                if success:
                                    logger.info(f"[{acc_id}] Relogged. Retrying post...")
                                    # Save state immediately
                                    await manager.save_state(acc_id, ctx)
                                    # Retry
                                    await posting_task(ctx, lst, content_engine)
                                    data_manager.mark_as_posted(lst, account_id=acc_id)
                                else:
                                    logger.error(f"[{acc_id}] Auto-login failed. Skipping.")
                            else:
                                raise

                    tasks.append(manager.run_account_task(account.account_id, task_wrapper))
                else:
                    logger.warning(f"Failed to generate listings for {account.city}")

            if tasks:
                logger.info(f"Executing {len(tasks)} posting tasks...")
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        logger.error(f"Task Failed: {res}")
            else:
                logger.info("No work available globally.")

            # 4. Anti-Spam / Scheduler Wait
            # In "Walk Away" mode, we wait significantly before the next batch check
            # For demo: 30 seconds. For Prod: 1 hour (3600)
            wait_time = 30 
            logger.info(f"Sleeping for {wait_time}s before next scheduler cycle...")
            await asyncio.sleep(wait_time)

    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
