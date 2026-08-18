import asyncio
import io
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi import UploadFile
from google.cloud import storage  # type: ignore
from google.cloud.exceptions import GoogleCloudError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Shared executor for ALL blocking GCS work. One pool per process.
_EXECUTOR = ThreadPoolExecutor(max_workers=10)


""" 
Google Cloud client libraries use Application Default Credentials (ADC). The library checks in this order (common cases):

GOOGLE_APPLICATION_CREDENTIALS environment variable — path to a service account JSON key file.
Example

export GOOGLE_APPLICATION_CREDENTIALS="/home/me/service-account.json"
"""


# Define the blocking operations to run in thread pool
def _blocking_upload(file_content: bytes, bucket_name: str, blob_name: str, content_type: str = "image/jpeg"):
    """
    Direct upload to GCS without PIL in-memory processing.
    Cloudflare handles resizing/optimization at the CDN edge.
    """
    client = _get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    file_obj = io.BytesIO(file_content)
    blob.upload_from_file(file_obj, content_type=content_type, timeout=30)

    return blob_name, content_type


async def upload_photo_to_storage(
    photo: UploadFile, listing_id: str, category: str = "general"
) -> str:
    """
    Upload photo to Google Cloud Storage and return public URL.

    FIXED: Now runs blocking I/O (PIL image processing and GCS upload)
    in a thread pool to avoid blocking the event loop.
    """
    try:
        # Validate file
        if not photo.content_type or not photo.content_type.startswith("image/"):
            raise ValueError("Only image files are allowed")

        if photo.size and photo.size > 5_000_000:  # 5MB limit
            raise ValueError("File size too large (max 5MB)")

        # Generate secure filename
        file_extension = photo.filename.split(".")[-1].lower() if photo.filename else "jpg"
        if file_extension not in ["jpg", "jpeg", "png", "webp"]:
            file_extension = "jpg"

        # Generate filename: category/YYYYMMDD_uuid.extension
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:12]  # Shorter UUID (12 chars)
        blob_name = f"{category.lower()}/{listing_id}_{timestamp}_{unique_id}.{file_extension}"

        bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "swapwithus-listing-images")

        # Reset file pointer to beginning
        await photo.seek(0)

        # Read file content into memory (async operation)
        file_content = await photo.read()

        # Run blocking operations in thread pool
        loop = asyncio.get_event_loop()
        blob_name, content_type = await loop.run_in_executor(
            _EXECUTOR,
            _blocking_upload,
            file_content,
            bucket_name,
            blob_name,
            photo.content_type or "image/jpeg",
        )

        # Return public URL
        public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

        logger.info(f"Successfully uploaded photo: {blob_name}")

        return public_url

    except GoogleCloudError as e:
        logger.error(f"Google Cloud Storage error: {e}", exc_info=True)
        raise Exception("Failed to upload photo: Storage service error")

    except Exception as e:
        logger.error(f"Photo upload error: {e}", exc_info=True)
        raise Exception("Failed to upload photo")





def _blocking_delete(public_url: str) -> bool:
    """
    Delete image from Google Cloud Storage using public URL.
    Blocking - only call from a thread pool, never directly on the event loop.
    Never raises: returns False on failure.
    """
    try:
        bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "swapwithus-listing-images")

        # Extract blob_name from public URL
        # Format: https://storage.googleapis.com/bucket-name/path/to/file.jpg
        blob_name = public_url.split(f"storage.googleapis.com/{bucket_name}/")[1]

        logger.info(f"Attempting to delete blob: {blob_name} from bucket: {bucket_name}")

        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()
        logger.info(f"Successfully deleted image: {blob_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete image from storage (URL: {public_url}): {e}", exc_info=True)
        # Don't raise - deletion failure shouldn't block listing deletion
        return False


async def delete_image_from_storage(public_url: str) -> bool:
    """
    Delete image from Google Cloud Storage without blocking the event loop.
    Never raises: returns False on failure.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_EXECUTOR, _blocking_delete, public_url)


async def delete_all_images_from_storage(image_urls: list[str]) -> bool:
    """
    Delete multiple images from Google Cloud Storage using their public URLs.

    FIXED: Now runs blocking GCS delete operation in thread pool.
    """
    import asyncio

    try:
        if not image_urls:
            return True

        loop = asyncio.get_event_loop()

        tasks = [
            loop.run_in_executor(_EXECUTOR, _blocking_delete, url) for url in image_urls if url
        ]
        results = await asyncio.gather(*tasks)

        # Check if all deletions succeeded
        all_success = all(results)
        if not all_success:
            failed_count = sum(1 for r in results if not r)
            logger.warning(f"Failed to delete {failed_count} out of {len(image_urls)} images")
            return False

        return True

    except Exception as e:
        logger.error(f"Failed to delete images from storage: {e}", exc_info=True)
        # Don't raise - deletion failure shouldn't block listing deletion
        return False


# Solution 1: Use Cloud CDN Signed Cookies (Highly Recommended)
# Of course. This is an excellent and very common performance problem. You've correctly identified that making a backend call to generate a signed URL for every single image is a major bottleneck. The user's browser has to wait for your server's response before it can even start fetching the image.

# Here is a breakdown of the problem and the best solutions, ordered from most recommended to least.

# The Core Problem: The Latency Chain
# Your current process looks like this:

# Frontend: "I need to display image.jpg."

# Frontend -> Backend: Makes an API call, "Please give me a URL for image.jpg."

# Backend:

# Receives the request.

# Uses its service account credentials to talk to Google Cloud Storage.

# Generates a unique, short-lived signed URL.

# Backend -> Frontend: Sends the signed URL back.

# Frontend: Finally receives the URL (https://storage.googleapis.com/...&Signature=...)

# Frontend -> Google CDN/GCS: Starts downloading the image.

# The delay is in steps 2, 3, and 4. You want to eliminate them as much as possible.

# Solution 1: Use Cloud CDN Signed Cookies (Highly Recommended)
# This is the most robust and scalable solution for your use case. Instead of authorizing access to one URL at a time, you grant the user a temporary "session pass" in the form of a cookie that allows them to access a whole set of files.

# How it Works:

# User Logs In (or starts a session): Your backend generates a single, cryptographically signed cookie. This cookie doesn't authorize a specific image, but rather a URL prefix, for example: https://your-cdn-domain.com/images/user/12345/*.

# Set the Cookie: Your backend sends this cookie to the user's browser with the Set-Cookie header.

# Frontend Requests Images: Now, your frontend can use regular, clean URLs in the HTML:

# HTML

# <img src="https://your-cdn-domain.com/images/user/12345/profile.jpg">
# <img src="https://your-cdn-domain.com/images/user/12345/post1.jpg">
# <img src="https://your-cdn-domain.com/images/user/12345/post2.jpg">
# CDN Validates: The browser automatically attaches the signed cookie to each request. The Google Cloud CDN edge nodes validate the cookie. If it's valid, the CDN serves the image (from its cache or from your GCS bucket). Your backend is never involved.



