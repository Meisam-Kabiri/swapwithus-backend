"""
Messaging Media Upload Service
Handles secure upload of images, videos, and audio for messaging
"""

import io
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Literal

from fastapi import UploadFile, HTTPException
from firebase_admin import storage

logger = logging.getLogger(__name__)

# File type configurations
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
ALLOWED_VIDEO_TYPES = ["video/mp4", "video/quicktime", "video/x-m4v", "video/webm"]
ALLOWED_AUDIO_TYPES = ["audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "audio/webm"]

# Size limits (in bytes)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB

_MESSAGING_EXECUTOR = ThreadPoolExecutor(max_workers=5)


def validate_media_file(file: UploadFile) -> Literal["image", "video", "audio"]:
    """Validate media file type and size"""
    if not file.content_type:
        raise HTTPException(status_code=400, detail="File type not specified")

    media_type = None
    max_size = 0

    if file.content_type in ALLOWED_IMAGE_TYPES:
        media_type = "image"
        max_size = MAX_IMAGE_SIZE
    elif file.content_type in ALLOWED_VIDEO_TYPES:
        media_type = "video"
        max_size = MAX_VIDEO_SIZE
    elif file.content_type in ALLOWED_AUDIO_TYPES:
        media_type = "audio"
        max_size = MAX_AUDIO_SIZE
    else:
        raise HTTPException(
            status_code=400,
            detail="File type not allowed. Allowed types: images, videos, audio"
        )

    if file.size and file.size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"{media_type.capitalize()} too large (max {max_size // 1024 // 1024}MB)"
        )

    return media_type


def _blocking_upload_media(
    file_content: bytes,
    conversation_id: str,
    media_type: Literal["image", "video", "audio"],
    original_filename: str,
    content_type: str
) -> str:
    """
    Blocking upload operation (runs in thread pool)
    """
    try:
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "swapwithus-project.firebasestorage.app")
        bucket = storage.bucket(bucket_name)

        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:12]
        file_extension = original_filename.split(".")[-1].lower() if original_filename else "dat"

        allowed_extensions = {
            "image": ["jpg", "jpeg", "png", "gif", "webp"],
            "video": ["mp4", "mov", "m4v", "webm"],
            "audio": ["mp3", "wav", "ogg", "webm", "m4a"]
        }

        if file_extension not in allowed_extensions.get(media_type, []):
            file_extension = {
                "image": "jpg",
                "video": "mp4",
                "audio": "mp3"
            }.get(media_type, "dat")

        blob_name = f"conversations/{conversation_id}/{timestamp}_{unique_id}.{file_extension}"

        # Direct upload to Firebase Storage (no PIL in-memory processing)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(file_content, content_type=content_type, timeout=60)

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(days=7),
            method="GET"
        )

        logger.info(f"Successfully uploaded {media_type} to {blob_name}")
        return signed_url

    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        raise Exception(f"Failed to upload {media_type}")


async def upload_message_media(
    file: UploadFile,
    conversation_id: str
) -> tuple[str, Literal["image", "video", "audio"]]:
    """
    Upload media file for messaging (async wrapper)
    """
    media_type = validate_media_file(file)

    await file.seek(0)
    file_content = await file.read()

    import asyncio
    loop = asyncio.get_event_loop()

    try:
        media_url = await loop.run_in_executor(
            _MESSAGING_EXECUTOR,
            _blocking_upload_media,
            file_content,
            conversation_id,
            media_type,
            file.filename or "unknown",
            file.content_type or "application/octet-stream"
        )

        return media_url, media_type

    except Exception as e:
        logger.error(f"Media upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
