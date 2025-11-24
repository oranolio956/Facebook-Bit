import json
import os
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from loguru import logger
from src.marketplace.models import RentalListing

class DataManager:
    """
    Manages data persistence:
    1. Assigns listings to accounts based on City/Location.
    2. Tracks posting history to prevent duplicates (even after restart).
    3. Manages the 'queue' of work.
    4. Tracks daily usage stats per account.
    """
    def __init__(self, listings_csv: str, history_file: str = "posting_history.json", stats_file: str = "daily_stats.json"):
        self.listings_csv = listings_csv
        self.history_file = history_file
        self.stats_file = stats_file
        self.history = self._load_json(self.history_file)
        self.stats = self._load_json(self.stats_file)

    def _load_json(self, filepath: str) -> Dict[str, Any]:
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_json(self, filepath: str, data: Dict[str, Any]):
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def save_history(self):
        self._save_json(self.history_file, self.history)
        
    def save_stats(self):
        self._save_json(self.stats_file, self.stats)

    def load_listings(self) -> List[RentalListing]:
        # ... existing implementation ...
        listings = []
        if not os.path.exists(self.listings_csv):
            return []
        
        with open(self.listings_csv, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Basic cleaning
                row = {k.strip(): v for k, v in row.items() if k}
                try:
                    listings.append(RentalListing(**row))
                except Exception as e:
                    logger.warning(f"Skipping bad row: {e}")
        return listings

    def check_daily_limit(self, account_id: str, max_posts: int) -> bool:
        """
        Checks if the account has reached its daily posting limit.
        Resets stats if the date has changed.
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Get account stats
        acc_stats = self.stats.get(account_id, {})
        last_date = acc_stats.get("last_date")
        
        # Reset if new day
        if last_date != today_str:
            acc_stats = {"last_date": today_str, "count": 0}
            self.stats[account_id] = acc_stats
            self.save_stats()
            
        return acc_stats["count"] < max_posts

    def increment_daily_count(self, account_id: str):
        """Increments the post count for today."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        acc_stats = self.stats.get(account_id, {"last_date": today_str, "count": 0})
        
        # Safety check date again
        if acc_stats.get("last_date") != today_str:
             acc_stats = {"last_date": today_str, "count": 0}
             
        acc_stats["count"] += 1
        self.stats[account_id] = acc_stats
        self.save_stats()

    def get_pending_listings_for_account(self, account_city: str, all_listings: List[RentalListing]) -> List[RentalListing]:
        # ... existing implementation ...
        """
        Returns listings that:
        1. Match the account's city (or contain it).
        2. Have NOT been posted in the last 24 hours.
        """
        pending = []
        now = datetime.now()
        
        for listing in all_listings:
            # 1. Geo-Match (Simple string check)
            if account_city.lower() not in listing.location.lower():
                continue

            # 2. Check History
            listing_id = f"{listing.title}_{listing.price}"
            last_posted_str = self.history.get(listing_id)
            if last_posted_str:
                last_posted = datetime.fromisoformat(last_posted_str)
                if now - last_posted < timedelta(hours=24):
                    continue
            
            pending.append(listing)
            
        return pending

    def mark_as_posted(self, listing: RentalListing, account_id: str = None):
        """Marks a listing as posted globally and increments account stats."""
        listing_id = f"{listing.title}_{listing.price}"
        self.history[listing_id] = datetime.now().isoformat()
        self.save_history()
        
        if account_id:
            self.increment_daily_count(account_id)
