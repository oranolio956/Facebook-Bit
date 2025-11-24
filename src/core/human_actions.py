import asyncio
import random
from typing import Optional
from playwright.async_api import Locator, Page

async def random_sleep(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """
    Asynchronously sleeps for a random duration between min_seconds and max_seconds.
    """
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)

async def human_type(locator: Locator, text: str, min_delay: int = 50, max_delay: int = 150) -> None:
    """
    Types text into a locator one character at a time with random delays between keystrokes.
    
    Args:
        locator: The Playwright Locator to type into.
        text: The text to type.
        min_delay: Minimum delay between keystrokes in milliseconds.
        max_delay: Maximum delay between keystrokes in milliseconds.
    """
    await locator.focus()
    
    for char in text:
        await locator.type(char, delay=0) # We handle delay ourselves
        delay_s = random.randint(min_delay, max_delay) / 1000.0
        await asyncio.sleep(delay_s)

async def random_scroll(page: Page, min_scroll: int = 300, max_scroll: int = 800) -> None:
    """
    Scrolls the page down a random amount, waits, and optionally scrolls up slightly.
    Mimics a user reading content.
    """
    # Randomly determine how much to scroll
    scroll_amount = random.randint(min_scroll, max_scroll)
    
    # Smooth scroll down
    # Playwright's mouse.wheel is good for this, or execute_script
    await page.mouse.wheel(0, scroll_amount)
    
    # Wait a bit (simulate reading)
    await random_sleep(1.0, 3.0)
    
    # 30% chance to scroll up slightly (re-reading previous line)
    if random.random() < 0.3:
        up_scroll = random.randint(50, 150)
        await page.mouse.wheel(0, -up_scroll)
        await random_sleep(0.5, 1.5)
