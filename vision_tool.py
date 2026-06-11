"""
vision_tool.py — Sarvam Document Intelligence wrapper for Khabar Suno.

Uses the official sarvamai SDK (AsyncDocumentIntelligenceClient) to:
  1. Create a digitization job (language=kn-IN, output_format=md)
  2. Save the uploaded image bytes to a temp file
  3. Upload the temp file to Sarvam's presigned URL
  4. Start + poll the job until complete
  5. Download the Markdown output
  6. Use Sarvam 30B LLM to turn the raw OCR into a natural Kannada narration

The READ_IMAGE_TOOL dict is the Pipecat function-calling schema.
"""

import asyncio
import os
import re
import tempfile
from typing import Optional
from pathlib import Path

import httpx
from loguru import logger

from image_store import image_store

SARVAM_BASE_URL = "https://api.sarvam.ai/v1"


# ── helpers ────────────────────────────────────────────────────────────────────

def _strip_html_tags(text: str) -> str:
    """Remove HTML tags, keep text content and whitespace."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s{2,}", " ", clean)
    return clean.strip()


def _language_for_image_name(filename: str) -> str:
    """
    Try to infer language from the uploaded filename hint.
    Defaults to 'kn-IN' (Kannada) for Khabar Suno.
    """
    fname = filename.lower()
    if "hindi" in fname or "hi_" in fname:
        return "hi-IN"
    if "english" in fname or "en_" in fname:
        return "en-IN"
    return "kn-IN"


async def _get_async_client():
    """Build the sarvamai AsyncSarvamAI client."""
    from sarvamai import AsyncSarvamAI
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY not set")
    return AsyncSarvamAI(api_subscription_key=api_key)


async def _call_llm_for_narration(ocr_text: str, filename: str) -> str:
    """
    Ask Sarvam 30B to turn raw OCR markdown into a natural Kannada narration.
    This adds the 'intelligence' on top of raw document digitization.
    """
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        return ocr_text

    system = (
        "You are Khabar Suno, a warm Kannada voice assistant. "
        "The user has shared an image and asked you to read it. "
        "You will receive raw OCR text extracted from that image. "
        "Your task: narrate it naturally in Kannada, as if reading it aloud to a friendly audience. "
        "Rules:\n"
        "- If the text is in English, read it in Kannada (translate key parts).\n"
        "- If the text is in Kannada/Hindi/other Indian scripts, read it as-is.\n"
        "- No bullet points, no markdown, no emojis — natural spoken sentences only.\n"
        "- If it looks like a newspaper: announce it like a radio bulletin.\n"
        "- If it looks like a medicine label: read the key instructions clearly.\n"
        "- If it looks like a notice or form: summarise the key points.\n"
        "- Keep it concise but complete — under 200 words.\n"
        "- End with: 'ಈ ಚಿತ್ರದಲ್ಲಿ ಬೇರೇನಾದರೂ ತಿಳಿಯಬೇಕೇ?' (Shall I tell you more about this image?)"
    )

    user_message = (
        f"Image filename: {filename}\n\n"
        f"Extracted text from the image:\n---\n{ocr_text[:2000]}\n---\n\n"
        "Please narrate this naturally in Kannada for the user to hear."
    )

    payload = {
        "model": "sarvam-30b",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 512,
        "temperature": 0.3,
    }

    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{SARVAM_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            narration = data["choices"][0]["message"]["content"].strip()
            logger.info(f"[Vision] LLM narration preview: {narration[:120]}...")
            return narration
    except Exception as e:
        logger.warning(f"[Vision] LLM narration failed, using raw OCR: {e}")
        return ocr_text


async def analyze_image(focus: str = "full") -> str:
    """
    Full vision pipeline:
      image_store → temp file → Sarvam Document Intelligence → LLM narration

    Returns a plain-text Kannada narration ready for TTS.
    """
    entry = await image_store.get()

    if entry is None:
        return (
            "ಯಾವುದೇ ಚಿತ್ರ ಅಪ್ಲೋಡ್ ಆಗಿಲ್ಲ. "
            "ದಯವಿಟ್ಟು ಮೊದಲು ಕ್ಯಾಮರಾ ಗುಂಡಿ ಒತ್ತಿ ಒಂದು ಚಿತ್ರ ಆಯ್ಕೆ ಮಾಡಿ. "
            "(No image uploaded yet. Please click the camera button and select an image first.)"
        )

    logger.info(
        f"[Vision] Processing image: {entry.filename} "
        f"({len(entry.data) // 1024} KB, {entry.content_type})"
    )

    # Map content_type to file extension
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
    }
    ext = ext_map.get(entry.content_type, ".jpg")

    # Determine language hint
    language = _language_for_image_name(entry.filename)
    logger.info(f"[Vision] Using language: {language}")

    tmp_path = None
    tmp_output = None
    try:
        # Step 1: Write image bytes to a temp file (SDK needs a file path)
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, prefix="khabarsuno_"
        ) as tmp:
            tmp.write(entry.data)
            tmp_path = tmp.name

        logger.info(f"[Vision] Temp file: {tmp_path}")

        # Step 2: Build async Sarvam client
        client = await _get_async_client()

        # Step 3: Create a document intelligence job
        job = await client.document_intelligence.create_job(
            language=language,
            output_format="md",  # markdown is easier to strip than html
        )
        logger.info(f"[Vision] Job created: {job.job_id}")

        # Step 4: Upload the temp image file
        await job.upload_file(tmp_path)
        logger.info(f"[Vision] File uploaded to job {job.job_id}")

        # Step 5: Start the job
        await job.start()
        logger.info(f"[Vision] Job started: {job.job_id}")

        # Step 6: Poll until complete (max 60s for image processing)
        status = await job.wait_until_complete(poll_interval=2.0, timeout=60.0)
        logger.info(f"[Vision] Job state: {status.job_state}")

        if status.job_state == "Failed":
            return (
                f"ಚಿತ್ರ ಪ್ರಕ್ರಿಯೆ ವಿಫಲವಾಯಿತು. "
                f"ದಯವಿಟ್ಟು ಸ್ಪಷ್ಟವಾದ ಚಿತ್ರ ಬಳಸಿ ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ. "
                "(Image processing failed. Please try with a clearer image.)"
            )

        # Step 7: Download the Markdown output (returned as a ZIP containing document.md)
        with tempfile.NamedTemporaryFile(
            suffix=".zip", delete=False, prefix="khabarsuno_out_"
        ) as out_tmp:
            tmp_output = out_tmp.name

        downloaded_path = await job.download_output(tmp_output)

        # The SDK returns a ZIP archive — extract document.md from it
        import zipfile
        raw_content = ""
        try:
            with zipfile.ZipFile(downloaded_path, "r") as zf:
                # Find the first .md or .html file inside
                md_files = [n for n in zf.namelist() if n.endswith((".md", ".html", ".txt"))]
                if md_files:
                    raw_content = zf.read(md_files[0]).decode("utf-8", errors="replace")
                else:
                    # Fallback: read the first file whatever it is
                    first = zf.namelist()[0] if zf.namelist() else None
                    if first:
                        raw_content = zf.read(first).decode("utf-8", errors="replace")
        except zipfile.BadZipFile:
            # Not a zip — read directly (older API versions)
            with open(downloaded_path, "r", encoding="utf-8", errors="replace") as f:
                raw_content = f.read()

        logger.info(
            f"[Vision] Downloaded output: {len(raw_content)} chars. "
            f"Preview: {raw_content[:200]!r}"
        )

        if not raw_content.strip():
            return (
                "ಚಿತ್ರದಲ್ಲಿ ಯಾವುದೇ ಪಠ್ಯ ಕಾಣಿಸಲಿಲ್ಲ. "
                "ದಯವಿಟ್ಟು ಸ್ಪಷ್ಟ ಅಕ್ಷರಗಳಿರುವ ಚಿತ್ರ ಬಳಸಿ. "
                "(No text detected in the image. Please use an image with clear, visible text.)"
            )

        # Step 8: Use LLM to create a natural Kannada narration
        if focus == "text_only":
            return raw_content[:1500]
        else:
            narration = await _call_llm_for_narration(raw_content, entry.filename)
            return narration

    except TimeoutError:
        logger.error("[Vision] Job timed out after 60s")
        return (
            "ಚಿತ್ರ ಪ್ರಕ್ರಿಯೆಗೆ ಹೆಚ್ಚು ಸಮಯ ತಗೆದುಕೊಳ್ಳುತ್ತಿದೆ. "
            "ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ. "
            "(Image processing is taking too long. Please try again.)"
        )
    except Exception as e:
        logger.error(f"[Vision] Pipeline error: {e}")
        return (
            f"ಚಿತ್ರ ವಿಶ್ಲೇಷಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. "
            f"ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ. "
            f"(Could not analyze image: {e})"
        )
    finally:
        # Clean up temp files
        for path in [tmp_path, tmp_output]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


# ── Pipecat function-calling schema ───────────────────────────────────────────

READ_IMAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_image",
        "description": (
            "Read, extract text from, and narrate the image that the user has uploaded. "
            "Call this when the user says things like: "
            "'ಈ ಚಿತ್ರ ಓದಿ', 'read this image', 'what does this say', "
            "'ಏನು ಬರೆದಿದೆ', 'ಚಿತ್ರ ನೋಡು', 'इसे पढ़ो', 'scan this', "
            "'what is in this picture', 'explain this image', 'ಓದಿ ಹೇಳು'. "
            "The tool uses Sarvam Vision to OCR any Indian-language text from the image "
            "and returns a natural Kannada narration ready for TTS."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "enum": ["full", "text_only"],
                    "description": (
                        "What to return: 'full' (natural narration, default), "
                        "'text_only' (raw extracted text without narration)."
                    ),
                }
            },
            "required": [],
        },
    },
}
