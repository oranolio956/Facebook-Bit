import asyncio
import random
from loguru import logger
from src.core.advanced_account_manager import AdvancedAccountManager, AccountConfig

async def mock_browsing_task(context):
    """
    Simulates a browsing session:
    - Go to a "check IP" like site (mocked via data url for speed/safety)
    - Set some session storage
    - Wait a bit
    """
    page = await context.new_page()
    
    # 1. Verify Geolocation/Proxy (conceptually)
    await page.goto("data:text/html,<html><body><h1>Checking IP...</h1></body></html>")
    await asyncio.sleep(1)
    
    # 2. Simulate User Interaction
    await page.evaluate("sessionStorage.setItem('last_action', 'viewed_listing_123')")
    await page.evaluate("sessionStorage.setItem('session_id', Math.random().toString())")
    
    # 3. Random Work
    work_time = random.uniform(2, 5)
    logger.info(f"Working for {work_time:.2f} seconds...")
    await asyncio.sleep(work_time)

async def main():
    logger.info("Starting Advanced Multi-Account Orchestration...")
    
    # 1. Setup Mock Accounts
    cities = ["New York", "London", "Tokyo", "Paris", "San Francisco"]
    accounts = []
    for i in range(10):
        city = cities[i % len(cities)]
        accounts.append(AccountConfig(
            account_id=f"user_{i+1:02d}",
            proxy_url=None, # In real usage: "http://user:pass@proxy:port"
            city=city,
            locale="en-US"
        ))
    
    # 2. Initialize Manager with max 5 concurrent slots
    manager = AdvancedAccountManager(accounts, max_concurrency=5)
    
    try:
        await manager.start()
        
        # 3. Create Tasks
        tasks = []
        for account in accounts:
            # We schedule all 10, but manager handles the 5-limit via semaphore
            tasks.append(
                manager.run_account_task(account.account_id, mock_browsing_task)
            )
            
        # 4. Run all efficiently
        logger.info(f"Queuing {len(tasks)} tasks...")
        await asyncio.gather(*tasks)
        
    except Exception as e:
        logger.critical(f"Orchestration failed: {e}")
    finally:
        await manager.stop()
        logger.info("All tasks finished.")

if __name__ == "__main__":
    asyncio.run(main())
