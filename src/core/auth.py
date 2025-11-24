import asyncio
import os
import sys
from loguru import logger
from src.core.browser import BrowserManager

# Configuration
USER_DATA_DIR = os.path.abspath("user_data")
SESSION_FILE = os.path.abspath("config/session.json")

async def main():
    logger.info("Starting authentication process...")
    
    # Initialize BrowserManager
    # Note: We are not passing storage_state_path here because we are establishing a new session.
    # We want to login manually and SAVE it.
    browser = BrowserManager(user_data_dir=USER_DATA_DIR, headless=False)
    
    try:
        await browser.start()
        page = await browser.get_page()
        
        logger.info("Navigating to Facebook...")
        await page.goto("https://facebook.com")
        
        logger.info("Checking login status...")
        
        # Check if already logged in (persistence from user_data_dir)
        # Selectors: 'a[aria-label="Home"]' or specific feed element
        is_logged_in = False
        try:
             # Fast check if we happen to be logged in
            await page.wait_for_selector('div[role="navigation"]', timeout=5000)
            is_logged_in = True
            logger.info("Already logged in (session persisted).")
        except:
            pass

        if not is_logged_in:
            logger.warning("Not logged in. waiting for manual login...")
            print("\n" + "="*50)
            print("ACTION REQUIRED: Please log in to Facebook manually in the browser window.")
            print("Solve any 2FA challenges.")
            print("The script is waiting for you to reach the home screen...")
            print("="*50 + "\n")
            
            # Loop until logged in
            while not is_logged_in:
                try:
                    # Look for common elements on the home feed/navigation
                    # 'div[role="navigation"]' is usually the left sidebar
                    # 'div[aria-label="Stories"]' is the stories tray
                    if await page.is_visible('div[role="navigation"]') or await page.is_visible('div[aria-label="Facebook"]'):
                         is_logged_in = True
                         break
                except Exception as e:
                    # Page might be navigating/reloading
                    pass
                
                await asyncio.sleep(2)
        
        logger.success("Login detected!")
        
        # Save storage state
        logger.info(f"Saving session to {SESSION_FILE}...")
        os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
        await browser.context.storage_state(path=SESSION_FILE)
        logger.success("Session saved successfully.")
        
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        logger.info("Closing browser...")
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
