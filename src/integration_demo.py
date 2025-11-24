import asyncio
import os
import shutil
from loguru import logger
from PIL import Image, ImageDraw

# Import our new engine
from src.core.content_engine import ContentEngine

async def create_dummy_image(path: str):
    """Creates a simple dummy image for testing."""
    img = Image.new('RGB', (800, 600), color = (73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((10,10), "Test Image", fill=(255, 255, 0))
    img.save(path)

async def main():
    logger.info("Starting Content Engine Integration Demo...")
    
    # 1. Initialize Engine
    engine = ContentEngine(processed_dir="temp_processed")
    
    # 2. Mock Listing Data
    raw_listing = {
        "address": "123 Main St",
        "base_price": 2500,
        "bedrooms": 2,
        "bathrooms": 2,
        "features": ["Gym", "Pool", "Doorman"]
    }
    
    # 3. Generate AI Content
    logger.info("--- Step 1: AI Text Generation ---")
    generated_content = await engine.generate_listing_content(raw_listing)
    print("\nGenerated Content:")
    print(f"Title: {generated_content['title']}")
    print(f"Description: {generated_content['description']}")
    print(f"Adjusted Price: {generated_content['price_logic']}")
    print(f"Tags: {generated_content['tags']}\n")
    
    # 4. Process Images (Digital Hygiene)
    logger.info("--- Step 2: Image Processing (Digital Hygiene) ---")
    
    # Create a dummy image to process
    dummy_source = "test_source_image.jpg"
    await create_dummy_image(dummy_source)
    
    # Process it
    cleaned_images = engine.process_images([dummy_source])
    
    if cleaned_images:
        logger.success(f"Successfully processed {len(cleaned_images)} images.")
        logger.info(f"New path: {cleaned_images[0]}")
    else:
        logger.error("Image processing failed.")
        
    # Cleanup
    if os.path.exists(dummy_source):
        os.remove(dummy_source)
    if os.path.exists("temp_processed"):
        shutil.rmtree("temp_processed")

    logger.info("Integration Demo Complete.")

if __name__ == "__main__":
    asyncio.run(main())
