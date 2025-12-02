"""
Messaging Media Upload Service
Handles secure upload of images, videos, and audio for messaging
"""

import io
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Literal, Tuple

from fastapi import UploadFile, HTTPException
from firebase_admin import storage
from PIL import Image

logger = logging.getLogger(__name__)

# File type configurations
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
ALLOWED_VIDEO_TYPES = ["video/mp4", "video/quicktime", "video/x-m4v", "video/webm"]
ALLOWED_AUDIO_TYPES = ["audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "audio/webm"]

# Size limits (in bytes)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB (increased from 20MB)
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB

# Image optimization settings
MAX_IMAGE_WIDTH = 1200
IMAGE_QUALITY = 85


def validate_media_file(file: UploadFile) -> Literal["image", "video", "audio"]:
    """
    Validate media file type and size

    Returns:
        str: Media type ("image", "video", or "audio")

    Raises:
        HTTPException: If file is invalid
    """
    if not file.content_type:
        raise HTTPException(status_code=400, detail="File type not specified")

    # Determine media type
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
            detail=f"File type not allowed. Allowed types: images, videos, audio"
        )

    # Validate file size
    if file.size and file.size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"{media_type.capitalize()} too large (max {max_size // 1024 // 1024}MB)"
        )

    return media_type


def optimize_image(image_bytes: bytes) -> Tuple[io.BytesIO, str]:
    """
    Optimize image for web (resize and compress)

    Returns:
        Tuple[io.BytesIO, str]: Optimized image bytes and content type
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        original_format = img.format

        # Resize if too large
        if img.width > MAX_IMAGE_WIDTH:
            ratio = MAX_IMAGE_WIDTH / img.width
            new_height = int(img.height * ratio)
            img = img.resize((MAX_IMAGE_WIDTH, new_height), Image.LANCZOS)

        output = io.BytesIO()

        # Optimize based on format
        if original_format == "PNG":
            has_transparency = img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            )

            if has_transparency:
                if img.mode == "P":
                    img = img.convert("RGBA")
                img.save(output, format="PNG", optimize=True)
                output.seek(0)
                return output, "image/png"
            else:
                # Convert to JPEG for smaller size
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                img.save(output, format="JPEG", quality=IMAGE_QUALITY, optimize=True)
                output.seek(0)
                return output, "image/jpeg"

        elif original_format == "WEBP":
            img.save(output, format="WEBP", quality=IMAGE_QUALITY, optimize=True)
            output.seek(0)
            return output, "image/webp"

        else:
            # JPEG or other formats
            if img.mode != "RGB":
                if img.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                else:
                    img = img.convert("RGB")

            img.save(output, format="JPEG", quality=IMAGE_QUALITY, optimize=True)
            output.seek(0)
            return output, "image/jpeg"

    except Exception as e:
        logger.error(f"Image optimization error: {e}")
        # Return original if optimization fails
        output = io.BytesIO(image_bytes)
        output.seek(0)
        return output, "image/jpeg"


def _blocking_upload_media(
    file_content: bytes,
    conversation_id: str,
    media_type: Literal["image", "video", "audio"],
    original_filename: str,
    content_type: str
) -> str:
    """
    Blocking upload operation (runs in thread pool)

    Returns:
        str: Firebase Storage download URL
    """
    try:
        # Get Firebase Storage bucket
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "swapwithus-project.firebasestorage.app")
        bucket = storage.bucket(bucket_name)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:12]
        file_extension = original_filename.split(".")[-1].lower() if original_filename else "dat"

        # Sanitize extension
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

        # Storage path: conversations/{conversation_id}/{timestamp}_{uuid}.{ext}
        blob_name = f"conversations/{conversation_id}/{timestamp}_{unique_id}.{file_extension}"

        # Optimize image if needed
        if media_type == "image":
            optimized_image, content_type = optimize_image(file_content)
            file_content = optimized_image.read()

        # Upload to Firebase Storage
        blob = bucket.blob(blob_name)
        blob.upload_from_string(file_content, content_type=content_type, timeout=60)

        # Option A: Make publicly accessible (fast but anyone can access)
        # blob.make_public()
        # public_url = blob.public_url

        # Option B: Use signed URLs (private, expires after 7 days)
        from datetime import timedelta
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
) -> Tuple[str, Literal["image", "video", "audio"]]:
    """
    Upload media file for messaging (async wrapper)

    Args:
        file: Uploaded file
        conversation_id: Conversation ID for organizing uploads

    Returns:
        Tuple[str, str]: (media_url, media_type)

    Raises:
        HTTPException: If upload fails
    """
    # Validate file
    media_type = validate_media_file(file)

    # Read file content
    await file.seek(0)
    file_content = await file.read()

    # Run blocking upload in thread pool
    import asyncio
    loop = asyncio.get_event_loop()

    try:
        media_url = await loop.run_in_executor(
            ThreadPoolExecutor(max_workers=5),
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
