import asyncio
import os
import random
from loguru import logger
from src.core.browser import BrowserManager
from src.marketplace.models import load_listings_from_csv, RentalListing
from src.marketplace.poster import start_new_listing, fill_listing_details, fill_advanced_details, publish_listing
from src.core.content_engine import ContentEngine

# Configuration
USER_DATA_DIR = os.path.abspath("user_data")
CSV_PATH = os.path.abspath("listings.csv")
PROCESSED_IMAGES_DIR = os.path.abspath("processed_images")
DRY_RUN = True  # Set to False to actually publish

async def main():
    logger.info("Starting Marketplace Automation Bot...")
    
    # 1. Load Listings
    if not os.path.exists(CSV_PATH):
        logger.error(f"Listings file not found at {CSV_PATH}. Please create it first.")
        return

    listings = load_listings_from_csv(CSV_PATH)
    logger.info(f"Loaded {len(listings)} listings from CSV.")
    
    if not listings:
        logger.warning("No listings found. Exiting.")
        return

    # 2. Initialize Engines
    # ContentEngine for Generative AI and Digital Hygiene
    content_engine = ContentEngine(processed_dir=PROCESSED_IMAGES_DIR)
    
    # BrowserManager assumes authentication is already handled and saved in user_data_dir via auth.py
    browser = BrowserManager(user_data_dir=USER_DATA_DIR, headless=False)
    
    try:
        await browser.start()
        page = await browser.get_page()
        
        # 3. Iterate through listings
        for i, original_listing in enumerate(listings):
            logger.info(f"\nProcessing Listing {i+1}/{len(listings)}: {original_listing.title}")
            
            try:
                # --- CONTENT GENERATION & HYGIENE PHASE ---
                logger.info("Generating unique AI content and sanitizing images...")
                
                # A. Generate Text
                # Convert Pydantic model to dict for prompt generation
                listing_dict = original_listing.model_dump()
                ai_content = await content_engine.generate_listing_content(listing_dict)
                
                # B. Process Images (Strip Exif, Resize/Hash)
                clean_images = content_engine.process_images(original_listing.images)
                
                if not clean_images:
                    logger.error("No valid images available after processing. Skipping listing.")
                    continue

                # C. Create a new "Clean" Listing Object
                # We update the original data with the AI-generated variations
                clean_listing = original_listing.model_copy(update={
                    "title": ai_content.get("title", original_listing.title),
                    "description": ai_content.get("description", original_listing.description),
                    "price": int(ai_content.get("price_logic", original_listing.price)),
                    "images": clean_images
                })
                
                logger.info(f"New Title: {clean_listing.title}")
                logger.info(f"New Price: {clean_listing.price}")
                
                # --- POSTING PHASE ---
                
                # Step 1: Start New Listing (Upload Images)
                await start_new_listing(page, clean_listing)
                
                # Step 2: Fill Details
                await fill_listing_details(page, clean_listing)
                
                # Step 3: Fill Advanced Details (Location, Type, Beds, Baths)
                await fill_advanced_details(page, clean_listing)
                
                # Step 4: Publish (or Dry Run)
                await publish_listing(page, dry_run=DRY_RUN)
                
                logger.success(f"Listing '{clean_listing.title}' processed successfully.")
                
                # Wait before next listing if not the last one
                if i < len(listings) - 1:
                    # Random sleep 10-20 minutes (600 - 1200 seconds)
                    wait_time = random.randint(600, 1200)
                    logger.info(f"Waiting {wait_time} seconds ({wait_time/60:.2f} minutes) before next post to avoid spam detection...")
                    await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Failed to process listing '{original_listing.title}': {e}")
                # Take screenshot for debugging
                screenshot_path = f"logs/error_{i}.png"
                await page.screenshot(path=screenshot_path)
                logger.info(f"Screenshot saved to {screenshot_path}")
                
                # Refresh page to reset state for next listing
                logger.info("Refreshing page and attempting to continue to next listing...")
                try:
                    await page.reload()
                    await asyncio.sleep(5)
                except:
                    # If reload fails, maybe browser crashed, try to restart
                    logger.critical("Browser seems unresponsive. Restarting...")
                    await browser.stop()
                    await browser.start()
                    page = await browser.get_page()

    except Exception as e:
        logger.critical(f"Critical bot failure: {e}")
    finally:
        logger.info("Bot finished. Closing browser.")
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
