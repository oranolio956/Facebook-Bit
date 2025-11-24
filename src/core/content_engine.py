import asyncio
import json
import os
import random
from typing import List, Dict, Any, Optional
from PIL import Image, ImageEnhance
from loguru import logger

# RUTHLESS AUDIT FIX: Removed Mock Client. 
# We now require the 'openai' library and a valid API key.
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

class ContentEngine:
    """
    Handles Generative AI content creation and Digital Hygiene for images.
    Production Mode: Requires OPENAI_API_KEY environment variable.
    """
    def __init__(self, processed_dir: str = "processed_images"):
        # RUTHLESS AUDIT FIX: Real API Client
        if not AsyncOpenAI:
             raise ImportError("Missing dependency 'openai'. Run: pip install openai")
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
             # We raise an error instead of mocking. 
             # If the user wants to run this, they MUST provide credentials.
             raise ValueError("OPENAI_API_KEY environment variable is not set.")
             
        self.llm_client = AsyncOpenAI(api_key=api_key)
        self.processed_dir = processed_dir
        self.personas = [
            "Professional Real Estate Agent: Formal, enthusiastic, and detail-oriented.",
            "Direct Owner: Casual, honest, and straight to the point.",
            "Property Manager: Efficient, focusing on policies and amenities.",
            "Lifestyle Marketer: Emotive, focusing on the 'vibe' and experience."
        ]
        
        os.makedirs(self.processed_dir, exist_ok=True)

    async def generate_listing_content(self, listing_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates unique listing content using an LLM with persona injection.
        """
        persona = random.choice(self.personas)
        logger.info(f"Generating content using persona: {persona}")
        
        system_prompt = f"""
        You are a {persona}.
        Your goal is to write a compelling rental listing description to avoid duplicate content detection filters.
        Output must be strict JSON with keys: title, description, price_logic, tags.
        """
        
        user_prompt = f"""
        Details: {json.dumps(listing_details)}
        Generate a unique title and description. 
        For price_logic, suggest a price slightly adjusted (e.g., +/- $10-50) from the base price to vary data.
        """
        
        try:
            # RUTHLESS AUDIT FIX: Real API Call
            response = await self.llm_client.chat.completions.create(
                model="gpt-3.5-turbo", # or gpt-4
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                response_format={ "type": "json_object" }
            )
            
            content_str = response.choices[0].message.content
            return json.loads(content_str)
            
        except Exception as e:
            logger.error(f"LLM Generation Failed: {e}")
            # RUTHLESS AUDIT FIX: Do not fall back to mock. Raise error to alert operator.
            raise RuntimeError(f"Content Generation failed: {e}")

    def process_images(self, image_paths: List[str]) -> List[str]:
        """
        Processes images to remove metadata (Exif) and ensure unique file hash.
        """
        processed_paths = []
        
        for idx, img_path in enumerate(image_paths):
            try:
                if not os.path.exists(img_path):
                    logger.warning(f"Image not found: {img_path}")
                    # Strict mode: If a source image is missing, we might want to fail the batch?
                    # For now, we skip it but log warning. 
                    continue
                
                with Image.open(img_path) as img:
                    # 1. Strip Metadata
                    # We create a new image without copying info/exif
                    data = list(img.getdata())
                    clean_img = Image.new(img.mode, img.size)
                    clean_img.putdata(data)
                    
                    # 2. Steganography / Hash Evasion
                    # Option A: Trivial Resize (99.9%)
                    width, height = clean_img.size
                    new_size = (int(width * 0.999), int(height * 0.999))
                    final_img = clean_img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # Save to processed directory
                    filename = f"processed_{random.randint(1000,9999)}_{os.path.basename(img_path)}"
                    save_path = os.path.join(self.processed_dir, filename)
                    
                    # Saving without 'exif' parameter ensures metadata is dropped
                    final_img.save(save_path, quality=95, optimize=True)
                    processed_paths.append(save_path)
                    logger.info(f"Processed image: {filename} (Metadata stripped, Hash modified)")
                    
            except Exception as e:
                logger.error(f"Failed to process image {img_path}: {e}")
                # RUTHLESS AUDIT FIX: We continue processing others, but if ALL fail, caller handles it.
        
        return processed_paths

    async def fetch_ai_images(self, prompt: str, count: int = 1) -> List[str]:
        """
        Generates images using OpenAI's DALL-E 3.
        Returns local paths to the saved images.
        """
        import requests
        import base64
        
        generated_paths = []
        logger.info(f"Generating {count} AI images with DALL-E 3 for: '{prompt[:50]}...'")
        
        try:
            # DALL-E 3 only generates 1 image per request usually, so we loop if count > 1
            for i in range(count):
                response = await self.llm_client.images.generate(
                    model="dall-e-3",
                    prompt=f"Interior photography of {prompt}. Real estate listing style, photorealistic, 4k, wide angle, natural lighting.",
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
                
                image_url = response.data[0].url
                
                # Download and Save
                # We save to processed_dir directly
                filename = f"gen_dalle3_{random.randint(10000, 99999)}.png"
                filepath = os.path.join(self.processed_dir, filename)
                
                # Request image data
                # Using standard requests here (synchronous) inside async func. 
                # For high volume, use aiohttp. For now, this is acceptable for 1-2 images.
                img_data = requests.get(image_url).content
                with open(filepath, 'wb') as f:
                    f.write(img_data)
                    
                # RUTHLESS AUDIT FIX: Process the generated image immediately (Hygiene)
                # DALL-E images have metadata and specific signatures. We strip them.
                clean_paths = self.process_images([filepath])
                if clean_paths:
                    # Remove the original "raw" DALL-E download to save space/evidence
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    generated_paths.append(clean_paths[0])
                else:
                    generated_paths.append(filepath) # Fallback if processing failed
                
        except Exception as e:
            logger.error(f"DALL-E Generation failed: {e}")
            # Do not raise, return empty list so we can try fallback or skip
        
        return generated_paths
