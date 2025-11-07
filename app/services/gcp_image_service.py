import io
import logging
import os
import uuid
from datetime import timedelta

from fastapi import UploadFile
from google.cloud import storage  # type: ignore
from google.cloud.exceptions import GoogleCloudError
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def optimize_image(image_file, max_width=1200, quality=85):
    """
    Smart image optimization:
    - PNG with transparency → optimized PNG
    - PNG without transparency → JPEG (smaller)
    - JPEG → optimized JPEG
    - WebP → optimized WebP
    - Other formats → JPEG
    """
    img = Image.open(image_file)
    original_format = img.format

    # Resize if too large
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    output = io.BytesIO()

    # Decide output format based on image characteristics
    if original_format == "PNG":
        # Check if PNG has transparency
        has_transparency = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        )

        if has_transparency:
            # Keep as PNG to preserve transparency
            if img.mode == "P":
                img = img.convert("RGBA")
            img.save(output, format="PNG", optimize=True)
            output.seek(0)
            return output, "image/png"
        else:
            # Convert to JPEG for smaller size
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=quality, optimize=True)
            output.seek(0)
            return output, "image/jpeg"

    elif original_format == "WEBP":
        # WebP is already efficient, keep it
        if img.mode in ("RGBA", "LA"):
            # WebP supports transparency, keep it
            img.save(output, format="WEBP", quality=quality, optimize=True, lossless=False)
        else:
            img.save(output, format="WEBP", quality=quality, optimize=True)
        output.seek(0)
        return output, "image/webp"

    else:
        # JPEG or other formats → convert to JPEG
        # Always convert to RGB for JPEG
        if img.mode != "RGB":
            if img.mode in ("RGBA", "LA"):
                # Create white background for transparency
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode == "P":
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")

        img.save(output, format="JPEG", quality=quality, optimize=True)
        output.seek(0)
        return output, "image/jpeg"


""" 
Google Cloud client libraries use Application Default Credentials (ADC). The library checks in this order (common cases):

GOOGLE_APPLICATION_CREDENTIALS environment variable — path to a service account JSON key file.
Example

export GOOGLE_APPLICATION_CREDENTIALS="/home/me/service-account.json"
"""


async def upload_photo_to_storage(
    photo: UploadFile, listing_id: str, category: str = "general"
) -> str:
    """Upload photo to Google Cloud Storage and return public URL"""
    try:
        # Validate file
        if not photo.content_type or not photo.content_type.startswith("image/"):
            raise ValueError("Only image files are allowed")

        if photo.size and photo.size > 5_000_000:  # 5MB limit
            raise ValueError("File size too large (max 5MB)")

        # Initialize Google Cloud Storage client
        client = storage.Client()
        bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "swapwithus-listing-images")
        bucket = client.bucket(bucket_name)

        # Generate secure filename
        file_extension = photo.filename.split(".")[-1].lower() if photo.filename else "jpg"
        if file_extension not in ["jpg", "jpeg", "png", "webp"]:
            file_extension = "jpg"

        # Generate filename: category/YYYYMMDD_uuid.extension
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:12]  # Shorter UUID (12 chars)
        blob_name = f"{category.lower()}/{listing_id}_{timestamp}_{unique_id}.{file_extension}"

        # Create blob and upload
        blob = bucket.blob(blob_name)

        # Reset file pointer to beginning
        await photo.seek(0)
        # Optimize image and get format
        optimized_image, content_type = optimize_image(photo.file, max_width=1200, quality=85)

        # Upload file with metadata
        blob.upload_from_file(optimized_image, content_type=content_type, timeout=30)

        # Note: Uniform bucket-level access is enabled, so no need for make_public()
        # The bucket should be configured for public read access at bucket level

        # Return public URL
        # cdn = "cdn.swapwithus.com"
        # cdn_url = f"https://{cdn}/{blob_name}"
        public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

        logger.info(f"Successfully uploaded photo: {blob_name}")

        return public_url

    except GoogleCloudError as e:
        logger.error(f"Google Cloud Storage error: {e}")
        raise Exception("Failed to upload photo: Storage service error")

    except Exception as e:
        logger.error(f"Photo upload error: {e}")
        raise Exception(f"Failed to upload photo: {str(e)}")


def get_signed_url(public_url: str, expires_seconds: int = 3600) -> str:
    """Convert public URL to signed URL using IAM-based signing (works on Cloud Run)"""
    try:
        bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "swapwithus-listing-images")

        # Extract blob_name from public URL
        blob_name = public_url.split(f"storage.googleapis.com/{bucket_name}/")[1]

        # Check if running on Cloud Run (no private key available)
        if os.getenv("K_SERVICE"):
            # Use IAM signBlob API - keyless signing on Cloud Run
            from google.auth import compute_engine
            from google.auth.transport import requests as google_requests

            service_account_email = (
                "swapwithus-backend-service@swapwithus-project.iam.gserviceaccount.com"
            )

            # Get access token from metadata server
            credentials = compute_engine.Credentials()
            auth_request = google_requests.Request()
            credentials.refresh(auth_request)
            access_token = credentials.token

            # Create client and blob
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            # Generate signed URL using IAM signBlob (no private key needed!)
            signed_url = blob.generate_signed_url(
                expiration=timedelta(seconds=expires_seconds),
                version="v4",
                service_account_email=service_account_email,
                access_token=access_token,
            )

            return signed_url
        else:
            # Local development - use standard signing
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            signed_url = blob.generate_signed_url(
                expiration=timedelta(seconds=expires_seconds), version="v4"
            )
            return signed_url

    except Exception as e:
        logger.error(f"CRITICAL: Failed to generate signed URL: {e}")
        # NEVER return public URLs - all images must remain private
        raise Exception(f"Cannot generate signed URL for private image: {str(e)}")


async def delete_image_from_storage(public_url: str) -> bool:
    """Delete image from Google Cloud Storage using public URL"""
    try:
        bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "swapwithus-listing-images")

        # Extract blob_name from public URL
        # Format: https://storage.googleapis.com/bucket-name/path/to/file.jpg
        blob_name = public_url.split(f"storage.googleapis.com/{bucket_name}/")[1]

        # Initialize storage client
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # Delete the blob
        blob.delete()

        logger.info(f"Successfully deleted image: {blob_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete image from storage: {e}")
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


# How to Implement:

# Enable Signed Cookies on your CDN Backend Service: In the Google Cloud Console, go to your Load Balancer / CDN settings and enable Signed Cookies for the backend service or backend bucket that points to your GCS bucket.

# Create a Signing Key: Create a key for your backend service. This is what your backend will use to sign the cookies.


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from app.utils.cdn_auth import make_urlprefix_token

    print("=" * 60)
    print("CDN URL SIGNING TEST")
    print("=" * 60)

    KEY_B64 = "TMLeUr9-SURjle9ky_jHnQ=="
    KEY_NAME = "cdnkey"
    blob_name = "2f884215-7155-49b1-8db1-14e0117cdbd1_20251014_60e31a1d-d04.png"
    cdn_base = "https://cdn.swapwithus.com/home/"

    print(f"Key Name: {KEY_NAME}")
    print(f"Key Value: {KEY_B64}")
    print(f"Testing image: {blob_name}\n")

    token = make_urlprefix_token(cdn_base, KEY_NAME, KEY_B64, expires_in=3600)
    signed_url = f"{cdn_base}{blob_name}?{token}"

    print("Signed URL:")
    print(signed_url)
    print("\nTest with curl:")
    print(f'curl -I "{signed_url}"')
