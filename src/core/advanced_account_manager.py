import asyncio
import json
import os
from typing import Dict, Any, Optional, List, Callable
from pydantic import BaseModel
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from loguru import logger

# Mock Geolocation Database for the example
CITY_COORDINATES = {
    "New York": {"latitude": 40.7128, "longitude": -74.0060},
    "London": {"latitude": 51.5074, "longitude": -0.1278},
    "Tokyo": {"latitude": 35.6762, "longitude": 139.6503},
    "Paris": {"latitude": 48.8566, "longitude": 2.3522},
    "San Francisco": {"latitude": 37.7749, "longitude": -122.4194},
}

class AccountConfig(BaseModel):
    account_id: str
    proxy_url: Optional[str]
    city: str
    locale: str = "en-US"
    username: Optional[str] = None
    password: Optional[str] = None
    totp_secret: Optional[str] = None # RUTHLESS AUDIT FIX: 2FA Secret
    max_posts_per_day: int = 5 # RUTHLESS AUDIT FIX: Daily Limit Safety

class AdvancedAccountManager:
    def __init__(self, accounts: List[AccountConfig], max_concurrency: int = 5, storage_dir: str = "user_data"):
        self.accounts = {acc.account_id: acc for acc in accounts}
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.storage_dir = storage_dir
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.banned_accounts = set() # Track dead accounts
        
        os.makedirs(self.storage_dir, exist_ok=True)
    
    async def _solve_2fa(self, page: Page, secret: str) -> bool:
        """Generates and enters 2FA code."""
        try:
            import pyotp
            totp = pyotp.TOTP(secret.replace(" ", ""))
            code = totp.now()
            
            logger.info(f"Solving 2FA with code: {code}")
            
            # Facebook 2FA input selectors vary
            # Sometimes it asks for 'approvals_code', sometimes split inputs
            input_selector = 'input[name="approvals_code"]'
            if not await page.locator(input_selector).is_visible():
                # Try looking for any numeric input or 'Code' label
                input_selector = 'input[type="text"]' # fallback risky but often works on 2fa page
            
            await page.fill(input_selector, code)
            
            # Click Continue/Submit
            # Look for button with type submit or text "Continue"
            submit_btn = page.locator('button[type="submit"]')
            if await submit_btn.is_visible():
                await submit_btn.click()
            else:
                # Try hitting Enter
                await page.press(input_selector, "Enter")
                
            await page.wait_for_load_state("networkidle")
            return True
        except Exception as e:
            logger.error(f"2FA Failed: {e}")
            return False

    async def check_account_health(self, context: BrowserContext, account_id: str) -> bool:
        """
        Navigates to Marketplace profile to check for bans/restrictions.
        """
        if account_id in self.banned_accounts:
            return False
            
        page = await context.new_page()
        try:
            # Go to Marketplace
            await page.goto("https://www.facebook.com/marketplace")
            await asyncio.sleep(2)
            
            # Check for Ban Banners
            # Text like: "Marketplace isn't available to you", "You can't buy or sell"
            content = await page.content()
            if "isn't available to you" in content or "limit reached" in content.lower():
                logger.critical(f"[{account_id}] ACCOUNT BANNED/RESTRICTED. Disabling.")
                self.banned_accounts.add(account_id)
                return False
                
            logger.info(f"[{account_id}] Health Check Passed.")
            return True
        except Exception as e:
            logger.warning(f"[{account_id}] Health check error: {e}")
            return True # Assume alive if check fails to allow retry
        finally:
            await page.close()

    async def start(self):
        """Initializes the Playwright browser instance."""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            # Launch options can be customized (headless=True/False)
            self.browser = await self.playwright.chromium.launch(
                headless=False, # RUTHLESS AUDIT FIX: Headless=False often safer for login
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"]
            )
            logger.info("Browser initialized.")

    async def stop(self):
        """Closes the browser and Playwright."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser shut down.")

    def _get_storage_paths(self, account_id: str):
        base = os.path.join(self.storage_dir, f"state_{account_id}")
        return {
            "state": f"{base}.json",
            "session": f"{base}_session.json"
        }
        
    async def perform_login(self, context: BrowserContext, account_id: str):
        """
        Attempts to log in using credentials + 2FA if the session is dead.
        """
        account = self.accounts.get(account_id)
        if not account or not account.username or not account.password:
            logger.warning(f"[{account_id}] Cannot auto-login: Missing credentials.")
            return False
            
        page = await context.new_page()
        try:
            logger.info(f"[{account_id}] Attempting Auto-Login...")
            await page.goto("https://facebook.com/login")
            await asyncio.sleep(2)
            
            if "login" not in page.url and await page.locator('div[role="navigation"]').is_visible():
                logger.info(f"[{account_id}] Already logged in.")
                return True

            # Fill Credentials
            await page.fill('input[name="email"]', account.username)
            await page.fill('input[name="pass"]', account.password)
            await page.click('button[name="login"]')
            await page.wait_for_load_state("networkidle")
            
            # RUTHLESS AUDIT FIX: Check for 2FA Checkpoint
            # URL often contains 'checkpoint' or 'two_step_verification'
            if "checkpoint" in page.url or await page.locator('input[name="approvals_code"]').is_visible():
                logger.warning(f"[{account_id}] 2FA Checkpoint detected!")
                if account.totp_secret:
                    success = await self._solve_2fa(page, account.totp_secret)
                    if not success:
                        return False
                else:
                    logger.error(f"[{account_id}] 2FA required but no Secret provided.")
                    return False

            # Verify Success
            try:
                await page.wait_for_selector('div[role="navigation"]', timeout=15000)
                logger.success(f"[{account_id}] Auto-Login Successful.")
                return True
            except:
                logger.error(f"[{account_id}] Login failed (Unknown state).")
                return False
                
        except Exception as e:
            logger.error(f"[{account_id}] Login Exception: {e}")
            return False
        finally:
            await page.close()

    async def load_context(self, account_id: str) -> BrowserContext:
        """
        Creates a context for the account, loading persistent state if available.
        Configures Proxy, Geolocation, and SessionStorage.
        """
        account = self.accounts.get(account_id)
        if not account:
            raise ValueError(f"Account {account_id} not configured.")

        paths = self._get_storage_paths(account_id)
        
        # Prepare Context Options
        context_options: Dict[str, Any] = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
            "locale": account.locale,
            "permissions": ["geolocation"],
        }

        # Sticky Proxy
        if account.proxy_url:
            context_options["proxy"] = {"server": account.proxy_url}

        # Geolocation Override
        geo = CITY_COORDINATES.get(account.city)
        if geo:
            context_options["geolocation"] = geo
            context_options["timezone_id"] = "America/New_York" # Simplified: in real app, map city to timezone
        
        # Load standard storageState (Cookies, LocalStorage)
        if os.path.exists(paths["state"]):
            context_options["storage_state"] = paths["state"]
            logger.debug(f"[{account_id}] Loaded storage state.")
        else:
            logger.debug(f"[{account_id}] No existing storage state. Creating fresh.")

        # Create Context
        context = await self.browser.new_context(**context_options)

        # Anti-detection script
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Inject Session Storage
        if os.path.exists(paths["session"]):
            try:
                with open(paths["session"], "r") as f:
                    session_data = json.load(f)
                
                if session_data:
                    injection_js = f"""
                        const data = {json.dumps(session_data)};
                        for (const key in data) {{
                            window.sessionStorage.setItem(key, data[key]);
                        }}
                    """
                    await context.add_init_script(injection_js)
                    logger.debug(f"[{account_id}] Injected session storage.")
            except Exception as e:
                logger.error(f"[{account_id}] Failed to load session storage: {e}")

        return context

    async def save_state(self, account_id: str, context: BrowserContext):
        """
        Saves the context state (Cookies, LocalStorage, SessionStorage) to disk.
        """
        paths = self._get_storage_paths(account_id)
        
        try:
            # Save standard state
            await context.storage_state(path=paths["state"])
            
            # Save Session Storage (requires accessing a page)
            if context.pages:
                page = context.pages[0]
                session_dump = await page.evaluate("""() => {
                    const data = {};
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        data[key] = sessionStorage.getItem(key);
                    }
                    return data;
                }""")
                
                with open(paths["session"], "w") as f:
                    json.dump(session_dump, f)
                logger.debug(f"[{account_id}] Saved full state.")
        except Exception as e:
            logger.error(f"[{account_id}] Failed to save state: {e}")

    async def run_account_task(self, account_id: str, task_func: Callable[[BrowserContext], Any]):
        """
        Executes a task for a specific account with concurrency control and state management.
        """
        async with self.semaphore:
            logger.info(f"[{account_id}] Acquired slot. Starting session...")
            context = None
            try:
                context = await self.load_context(account_id)
                
                # Run the task
                await task_func(context)
                
                # Save state after success
                await self.save_state(account_id, context)
                logger.success(f"[{account_id}] Task completed successfully.")
                
            except Exception as e:
                logger.error(f"[{account_id}] Session failed: {e}")
                raise
            finally:
                if context:
                    await context.close()
                logger.info(f"[{account_id}] Released slot.")
