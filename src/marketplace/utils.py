import asyncio
from playwright.async_api import Page, Locator
from loguru import logger
from src.core.human_actions import random_sleep

async def dismiss_popups(page: Page):
    """
    Aggressively closes common Facebook popups/modals that block interaction.
    """
    # Common selectors for "Close", "Dismiss", "Not Now", "Save Draft" dialogs
    popup_selectors = [
        'div[aria-label="Close"]',
        'div[aria-label="Dismiss"]',
        'span:has-text("Not Now")',
        'span:has-text("Discard")', # If "Continue editing?" appears
        'div[role="dialog"] div[aria-label="Close"]'
    ]
    
    for selector in popup_selectors:
        try:
            # Check for visibility without waiting (fail fast)
            if await page.locator(selector).is_visible():
                logger.info(f"Blocking popup detected ({selector}). Dismissing...")
                await page.locator(selector).click()
                await random_sleep(0.5, 1.0)
        except:
            pass

async def safe_clear_input(locator: Locator):
    """
    Reliably clears an input field, handling React-controlled inputs where .fill('') might fail.
    """
    try:
        await locator.click()
        # Select all text and delete
        await locator.press("Control+A")
        await locator.press("Backspace")
        # Double check with fill
        await locator.fill("")
    except Exception as e:
        logger.warning(f"Failed to clear input: {e}")

async def wait_for_valid_state(page: Page, next_step_selector: str):
    """
    Checks if we are blocked by form errors after trying to proceed.
    """
    # Check for common error messages
    error_selectors = [
        'span:has-text("Required")', 
        'span:has-text("Please enter")', 
        'div[role="alert"]'
    ]
    
    for err in error_selectors:
        if await page.locator(err).is_visible():
            text = await page.locator(err).text_content()
            raise ValueError(f"Form Error Detected: {text}")
