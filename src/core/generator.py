import json
import random
from typing import List, Dict, Any
from loguru import logger
# Reuse the existing ContentEngine which holds the OpenAI client
from src.core.content_engine import ContentEngine

class ListingGenerator:
    """
    Generates synthetic rental listings data from scratch using LLMs.
    """
    def __init__(self, content_engine: ContentEngine):
        self.engine = content_engine

    async def generate_listings(self, city: str, count: int = 1) -> List[Dict[str, Any]]:
        """
        Creates 'count' synthetic listings for a specific city.
        """
        listings = []
        logger.info(f"Generating {count} synthetic listings for {city}...")

        system_prompt = """
        You are a Real Estate Database Generator.
        Generate realistic, diverse rental listing metadata.
        Output must be a JSON object containing a list of listings under the key 'listings'.
        Each listing must have: title, description, price (integer), bedrooms (int), bathrooms (float), location (specific neighborhood in the city), address (realistic but fictional).
        """

        for _ in range(count):
            # We generate 1 by 1 or batches. For robustness, 1 by 1 or small batches is safer for JSON parsing.
            user_prompt = f"""
            Generate 1 realistic rental listing for {city}.
            Vary the style (Luxury, Budget, Student, Family).
            Ensure the address implies the city: {city}.
            """
            
            try:
                response = await self.engine.llm_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.8,
                    response_format={ "type": "json_object" }
                )
                
                data = json.loads(response.choices[0].message.content)
                # Handle if LLM returns a list or single object wrapped in 'listings'
                items = data.get('listings', [data])
                
                for item in items:
                    # Normalize keys
                    listing = {
                        "title": item.get("title"),
                        "price": item.get("price"),
                        "description": item.get("description"),
                        "location": item.get("location", city), # Fallback to city
                        "bedrooms": item.get("bedrooms", 1),
                        "bathrooms": item.get("bathrooms", 1.0),
                        "images": [], # Will be filled by Image Generator
                        "category": "Property for Rent"
                    }
                    listings.append(listing)
                    
            except Exception as e:
                logger.error(f"Failed to generate synthetic listing: {e}")
                
        return listings
