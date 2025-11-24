import csv
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

class RentalListing(BaseModel):
    title: str
    price: int
    description: str
    images: List[str]
    location: str
    category: str = "Property for Rent"
    bedrooms: int
    bathrooms: float

    @field_validator('images', mode='before')
    @classmethod
    def split_images(cls, v):
        if isinstance(v, str):
            # Assumes images are separated by | or , in CSV
            if "|" in v:
                return [img.strip() for img in v.split("|")]
            return [img.strip() for img in v.split(",")]
        return v

def load_listings_from_csv(file_path: str) -> List[RentalListing]:
    """
    Reads a CSV file and converts rows into RentalListing objects.
    Expected CSV columns: title, price, description, images, location, bedrooms, bathrooms, [category]
    """
    listings = []
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle type conversion for numeric fields if they come in as strings from CSV
            # Pydantic does this automatically if passing to constructor, but we need to ensure keys match
            
            # Map or clean keys if necessary, strictly assuming CSV headers match model fields
            # For robustness, we might want to strip whitespace from keys
            row = {k.strip(): v for k, v in row.items() if k}
            
            try:
                listing = RentalListing(**row)
                listings.append(listing)
            except Exception as e:
                print(f"Skipping invalid row: {row} - Error: {e}")
                
    return listings
