import asyncio
import json
import os
from typing import Dict, List, Optional
from pydantic import BaseModel

class Account(BaseModel):
    username: str
    password: str
    proxy_url: Optional[str] = None
    city: str
    user_data_dir: str
    storage_state_path: str
    session_storage_path: Optional[str] = None

class AccountManager:
    """
    Manages a pool of accounts with concurrency control.
    Enforces 'Sticky Proxy' by keeping the proxy association in the Account model.
    """
    def __init__(self, accounts: List[Account], max_concurrency: int = 5):
        self.accounts: Dict[str, Account] = {acc.username: acc for acc in accounts}
        self.semaphore = asyncio.Semaphore(max_concurrency)
        
    def get_account(self, username: str) -> Optional[Account]:
        return self.accounts.get(username)
    
    def get_all_accounts(self) -> List[Account]:
        return list(self.accounts.values())
        
    async def acquire_slot(self):
        """Acquires a concurrency slot."""
        await self.semaphore.acquire()
        
    def release_slot(self):
        """Releases a concurrency slot."""
        self.semaphore.release()

    def add_account(self, account: Account):
        self.accounts[account.username] = account

    # Helper to load from CSV could go here, keeping it simple for now as per instructions
