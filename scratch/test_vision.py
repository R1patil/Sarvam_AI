"""
scratch/test_vision.py — Quick standalone test for the Sarvam Vision API.

Usage:
  1. Add a test image to d:/khabar-suno/scratch/test_image.jpg (or change TEST_IMAGE_PATH below)
  2. From the project root, run:
       python scratch/test_vision.py

This calls analyze_image() directly (not via Pipecat) so you can verify
the Vision API is working before running the full bot.
"""

import asyncio
import os
import sys

# Fix Windows console encoding for emoji/Kannada output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Allow importing from the parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

# Point this at any image you want to test
TEST_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "test_image.jpg")


async def main():
    from image_store import image_store
    from vision_tool import analyze_image

    # Check we have a test image
    if not os.path.exists(TEST_IMAGE_PATH):
        print(f"⚠️  No test image found at: {TEST_IMAGE_PATH}")
        print("   Please add a test image (e.g. a Kannada newspaper photo) and rerun.")
        print()
        print("   Alternatively, running with a dummy 1x1 pixel image for API connectivity check...")

        # Create a minimal 1x1 white JPEG to test API connectivity
        import base64
        # Minimal valid JPEG (1x1 white pixel)
        tiny_jpeg = base64.b64decode(
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoH"
            "BwYIDAoMCwsKCwsNCxAQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQME"
            "BAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU"
            "FBQUFBT/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQ"
            "AQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAA"
            "AAAAAAAAAAAP/aAAwDAQACEQMRAD8AJQAB/9k="
        )
        await image_store.set("test_pixel.jpg", "image/jpeg", tiny_jpeg)
        print("   [Using 1x1 pixel test image]")
    else:
        with open(TEST_IMAGE_PATH, "rb") as f:
            data = f.read()

        # Guess mime type from extension
        ext = TEST_IMAGE_PATH.rsplit(".", 1)[-1].lower()
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                    "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp"}
        mime = mime_map.get(ext, "image/jpeg")

        await image_store.set(os.path.basename(TEST_IMAGE_PATH), mime, data)
        print(f"✅ Loaded test image: {TEST_IMAGE_PATH} ({len(data)//1024} KB, {mime})")

    print()
    print("🔍 Calling Sarvam Vision API...")
    print("-" * 60)

    result = await analyze_image()

    print(result)
    print("-" * 60)
    print("✅ Vision test complete!")


if __name__ == "__main__":
    asyncio.run(main())
