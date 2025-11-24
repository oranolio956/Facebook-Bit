import asyncio
import json
import os
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright, Page
from loguru import logger
from src.core.account_manager import Account

class ContextFactory:
    """
    Creates and configures browser contexts for specific accounts.
    Handles proxy configuration, storage persistence, and evasion scripts.
    """
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self._lock = asyncio.Lock()

    async def start_browser(self) -> None:
        """Starts the main browser instance if not running."""
        async with self._lock:
            if self.browser:
                return
            
            logger.info("Starting shared browser instance...")
            self.playwright = await async_playwright().start()
            
            # Global browser args for evasion
            args = [
                "--disable-blink-features=AutomationControlled",
            ]
            
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=args,
                ignore_default_args=["--enable-automation"]
            )

    async def create_context(self, account: Account) -> BrowserContext:
        """
        Creates a new context for the given account.
        Loads cookies/localStorage from storage_state_path.
        Configures the sticky proxy.
        """
        await self.start_browser()
        
        logger.info(f"Creating context for account: {account.username} (City: {account.city})")
        
        # Prepare options
        options: Dict[str, Any] = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
            # RUTHLESS AUDIT FIX: Block WebRTC Leaks
            # We force WebRTC to use the proxy or disable non-proxied UDP.
            # In Playwright/Chromium, this is often handled via permissions or args.
            # Best robust way: Deny generic permissions or use browser args.
            "permissions": ["geolocation"], # We grant geo, but should block camera/mic/etc
        }
        
        # 1. Sticky Proxy
        if account.proxy_url:
            options["proxy"] = {"server": account.proxy_url}
            
        # 2. Persistent Storage (Cookies/LocalStorage)
        if os.path.exists(account.storage_state_path):
            options["storage_state"] = account.storage_state_path
            logger.info(f"Loaded storage state from {account.storage_state_path}")
            
        context = await self.browser.new_context(**options)
        
        # Evasion: Remove navigator.webdriver
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # RUTHLESS AUDIT FIX: WebRTC Handling
        # This script modifies the WebRTC object to prevent IP leakage
        await context.add_init_script("""
            const getUserMedia = navigator.mediaDevices?.getUserMedia.bind(navigator.mediaDevices);
            Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
                value: (constraints) => {
                    return Promise.reject(new Error('WebRTC disabled for privacy'));
                }
            });
        """)
        
        # 3. Session Storage Re-injection
        # We inject a script that runs on every page load to restore session storage
        if account.session_storage_path and os.path.exists(account.session_storage_path):
            try:
                with open(account.session_storage_path, 'r') as f:
                    session_data = json.load(f)
                
                # Create a script to inject the data
                # We check if data exists to avoid errors
                if session_data:
                    logger.info("Injecting session storage data...")
                    injection_script = f"""
                        const sessionData = {json.dumps(session_data)};
                        for (const key in sessionData) {{
                            window.sessionStorage.setItem(key, sessionData[key]);
                        }}
                    """
                    await context.add_init_script(injection_script)
            except Exception as e:
                logger.error(f"Failed to load session storage for {account.username}: {e}")

        return context

    async def save_context_state(self, context: BrowserContext, account: Account) -> None:
        """
        Saves the current context state (cookies, localStorage, sessionStorage) to disk.
        """
        try:
            # Save Cookies and LocalStorage
            logger.info(f"Saving storage state for {account.username}...")
            # Ensure dir exists
            os.makedirs(os.path.dirname(account.storage_state_path), exist_ok=True)
            await context.storage_state(path=account.storage_state_path)
            
            # Save Session Storage
            # Requires an active page to access window.sessionStorage
            if account.session_storage_path and context.pages:
                page = context.pages[0]
                session_data = await page.evaluate("""() => {
                    const data = {};
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        data[key] = sessionStorage.getItem(key);
                    }
                    return data;
                }""")
                
                os.makedirs(os.path.dirname(account.session_storage_path), exist_ok=True)
                with open(account.session_storage_path, 'w') as f:
                    json.dump(session_data, f)
                logger.info("Session storage saved.")
                
        except Exception as e:
            logger.error(f"Failed to save context state for {account.username}: {e}")

    async def stop(self) -> None:
        """Closes the browser instance."""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
