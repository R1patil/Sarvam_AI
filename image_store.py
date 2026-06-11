"""
image_store.py — Simple in-memory store for the last uploaded image.

The /upload-image FastAPI route writes here.
The read_image Pipecat tool reads from here.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageEntry:
    filename: str
    content_type: str
    data: bytes  # raw bytes


class ImageStore:
    """Thread-safe (asyncio-safe) singleton store for latest uploaded image."""

    def __init__(self) -> None:
        self._entry: Optional[ImageEntry] = None
        self._lock = asyncio.Lock()

    async def set(self, filename: str, content_type: str, data: bytes) -> None:
        async with self._lock:
            self._entry = ImageEntry(
                filename=filename,
                content_type=content_type,
                data=data,
            )

    async def get(self) -> Optional[ImageEntry]:
        async with self._lock:
            return self._entry

    async def clear(self) -> None:
        async with self._lock:
            self._entry = None

    def has_image(self) -> bool:
        return self._entry is not None


# Module-level singleton — imported by both server.py and vision_tool.py
image_store = ImageStore()
