import asyncio
import os
from loguru import logger
from playwright.async_api import Page, Locator
from src.marketplace.models import RentalListing
from src.core.human_actions import random_sleep, human_type
from src.marketplace.utils import dismiss_popups, safe_clear_input, wait_for_valid_state

async def start_new_listing(page: Page, listing: RentalListing):
    """
    Navigates to the Marketplace rental creation page and uploads images.
    Robustness: Handles 'Resume Draft' dialogs and verifies uploads.
    """
    url = "https://www.facebook.com/marketplace/create/rental"
    logger.info(f"Navigating to {url}...")
    
    await page.goto(url)
    
    # RUTHLESS AUDIT FIX: Handle "Continue editing?" or "Discard draft?"
    # If we land on a page that isn't empty, we might need to reset.
    await random_sleep(2, 4)
    await dismiss_popups(page)

    logger.info("Page loaded. Attempting to upload images...")
    
    # Verify images exist locally
    valid_images = []
    for img_path in listing.images:
        if os.path.exists(img_path):
            valid_images.append(os.path.abspath(img_path))
        else:
            logger.warning(f"Image not found: {img_path}")
            
    if not valid_images:
        raise ValueError("No valid images found to upload.")

    # RUTHLESS AUDIT FIX: Check if images are already present (Draft Trap)
    # If so, we should remove them or we might duplicate. 
    # For now, simplistic approach: Uploading usually appends.
    # Ideally, we find "Remove" buttons and click them all first.
    try:
        remove_btns = await page.locator('div[aria-label="Remove"]').all()
        if remove_btns:
            logger.info(f"Found {len(remove_btns)} existing images (Draft). Clearing...")
            for btn in remove_btns:
                if await btn.is_visible():
                    await btn.click()
                    await random_sleep(0.5, 1)
    except:
        pass

    # Upload files
    file_input_selector = 'input[type="file"]'
    await page.set_input_files(file_input_selector, valid_images)
    logger.info(f"Sent {len(valid_images)} images to input.")
    
    # RUTHLESS AUDIT FIX: Explicit wait for upload success OR failure
    # Wait for at least one "Remove" button to appear (indicating success)
    try:
         await page.wait_for_selector('div[aria-label="Remove"]', timeout=45000)
         logger.success("Images uploaded and visible in preview.")
    except Exception:
        # Check for error toast
        if await page.locator('div[role="alert"]').is_visible():
            err_text = await page.locator('div[role="alert"]').text_content()
            raise RuntimeError(f"Facebook blocked the upload: {err_text}")
        logger.warning("Could not verify image previews, but proceeding cautiously.")

async def fill_listing_details(page: Page, listing: RentalListing):
    """
    Fills out basic details.
    Robustness: Clears inputs first to prevent appending to drafts. Use selector fallbacks.
    """
    logger.info("Filling listing details...")
    await dismiss_popups(page)
    
    try:
        # --- TITLE ---
        # Selector Waterfall
        title_selectors = [
            page.get_by_label("Title"),
            page.get_by_role("textbox", name="Title"),
            page.get_by_placeholder("Title"),
            page.get_by_role("textbox", name="What are you selling?") # Sometimes used
        ]
        
        title_locator = None
        for sel in title_selectors:
            if await sel.is_visible():
                title_locator = sel
                break
        
        if not title_locator:
            raise ValueError("Could not find Title input field.")

        logger.info(f"Typing Title: {listing.title}")
        await safe_clear_input(title_locator) # Prevent Draft Appending
        await human_type(title_locator, listing.title)
        await random_sleep(0.5, 1.5)

        # --- PRICE ---
        logger.info(f"Typing Price: {listing.price}")
        price_locator = page.get_by_label("Price")
        if not await price_locator.is_visible():
            price_locator = page.get_by_role("textbox", name="Price")
            
        await safe_clear_input(price_locator)
        await human_type(price_locator, str(listing.price))
        await random_sleep(0.5, 1.5)
        
        # --- DESCRIPTION ---
        logger.info("Typing Description...")
        desc_locator = page.get_by_label("Description")
        if not await desc_locator.is_visible():
            desc_locator = page.get_by_role("textbox", name="Description")
            
        await safe_clear_input(desc_locator)
        await human_type(desc_locator, listing.description)
        await random_sleep(0.5, 1.5)
        
        logger.success("Basic details filled.")

    except Exception as e:
        logger.error(f"Failed to fill listing details: {e}")
        raise

async def fill_advanced_details(page: Page, listing: RentalListing):
    """
    Fills out advanced details.
    Robustness: Handles dropdown glitches and verifies clicks.
    """
    logger.info("Filling advanced details...")
    await dismiss_popups(page)

    try:
        # --- LOCATION ---
        logger.info(f"Setting Location: {listing.location}")
        location_input = page.get_by_label("Location")
        if not await location_input.is_visible():
            location_input = page.get_by_role("textbox", name="Location")
        
        # Need to be careful clearing location, sometimes it resets map
        await location_input.click()
        await location_input.fill(listing.location) # fill is safer than type for location search
        await random_sleep(1, 2)
        
        # Wait for suggestions
        try:
             await page.wait_for_selector('ul[role="listbox"], div[role="listbox"]', timeout=5000)
             first_option = page.locator('[role="option"]').first
             await first_option.click()
             await random_sleep(0.5, 1.5)
        except Exception:
             logger.warning("Location dropdown issue. Hitting Enter as fallback.")
             await location_input.press("Enter")

        # --- RENTAL TYPE ---
        # Logic: Try to find the dropdown. If already set (Draft), verify value? 
        # For simplicity, we re-set it.
        logger.info("Setting Rental Type...")
        type_trigger = page.get_by_label("Rental type")
        if not await type_trigger.is_visible():
             type_trigger = page.get_by_label("Property type")
        
        if await type_trigger.is_visible():
             await type_trigger.click()
             await random_sleep(0.5, 1.0)
             
             target_type = "Apartment/Condo"
             if "house" in listing.category.lower():
                 target_type = "House"
                 
             # Try to click exact text, fallback to partial
             try:
                await page.get_by_role("option", name=target_type).first.click()
             except:
                logger.warning(f"Could not find exact match for {target_type}, picking first option.")
                await page.locator('[role="option"]').first.click()
             
             await random_sleep(0.5, 1.5)

        # --- BED/BATH ---
        # (Same logic as before, but wrapped in try/except for optionality)
        try:
            bed_trigger = page.get_by_label("Bedrooms")
            if await bed_trigger.is_visible():
                await bed_trigger.click()
                await random_sleep(0.5, 1)
                await page.get_by_role("option", name=str(listing.bedrooms), exact=True).click()
        except Exception as e:
            logger.warning(f"Skipping Bedrooms (not found/glitch): {e}")

        try:
            bath_trigger = page.get_by_label("Bathrooms")
            if await bath_trigger.is_visible():
                await bath_trigger.click()
                await random_sleep(0.5, 1)
                bath_text = str(listing.bathrooms).replace(".0", "")
                await page.get_by_role("option", name=bath_text, exact=True).click()
        except Exception as e:
            logger.warning(f"Skipping Bathrooms: {e}")

    except Exception as e:
        logger.error(f"Failed to fill advanced details: {e}")
        raise

async def publish_listing(page: Page, dry_run: bool = True):
    """
    Finalizes and publishes.
    Robustness: Handles 'Next' loops, Validation Errors, and Confirmations.
    """
    logger.info("Finalizing listing...")
    
    try:
        # Loop "Next" until "Publish" is found
        max_attempts = 5
        for attempt in range(max_attempts):
            await dismiss_popups(page)
            
            # Check for Publish
            publish_btn = page.get_by_label("Publish")
            if not await publish_btn.is_visible():
                 publish_btn = page.get_by_role("button", name="Publish")
            
            if await publish_btn.is_visible():
                logger.info("Publish button found.")
                break
            
            # Check for Next
            next_btn = page.get_by_label("Next")
            if not await next_btn.is_visible():
                 next_btn = page.get_by_role("button", name="Next")
            
            if await next_btn.is_visible():
                logger.info(f"Clicking Next (Attempt {attempt+1})...")
                await next_btn.click()
                await random_sleep(2, 3)
                
                # RUTHLESS AUDIT FIX: Check for Validation Errors blocking progress
                try:
                    await wait_for_valid_state(page, "")
                except ValueError as ve:
                    logger.error(f"Validation Error preventing Next: {ve}")
                    raise
            else:
                # If neither Next nor Publish...
                logger.warning("Neither Next nor Publish button visible. Waiting...")
                await asyncio.sleep(2)

        # --- PUBLISH STEP ---
        publish_btn = page.get_by_label("Publish")
        if not await publish_btn.is_visible():
            publish_btn = page.get_by_role("button", name="Publish")

        if not await publish_btn.is_visible():
            raise RuntimeError("Stuck in wizard: Could not reach Publish button.")

        if dry_run:
            logger.warning("DRY RUN: Highlighting Publish button but NOT clicking.")
            await publish_btn.evaluate("el => el.style.border = '5px solid red'")
            await random_sleep(5, 5)
        else:
            logger.info("Clicking Publish...")
            await publish_btn.click()
            
            # RUTHLESS AUDIT FIX: Wait for specific success indicators
            try:
                # 1. Look for success modal text
                await page.wait_for_selector('text=Listing Published', timeout=15000)
                logger.success("Listing published successfully!")
            except:
                # 2. Check URL change (often redirects to /marketplace/you/selling)
                if "selling" in page.url:
                    logger.success("Redirected to Selling dashboard. Success assumed.")
                else:
                    logger.warning("Confirmation not detected, but no error found.")

    except Exception as e:
        logger.error(f"Failed to publish listing: {e}")
        raise
