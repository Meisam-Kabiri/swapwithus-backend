import os
import uuid
from typing import Tuple, Optional
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
import aiohttp
import asyncio
import logging
from fastapi import UploadFile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

""" 
Google Cloud client libraries use Application Default Credentials (ADC). The library checks in this order (common cases):

GOOGLE_APPLICATION_CREDENTIALS environment variable — path to a service account JSON key file.
Example

export GOOGLE_APPLICATION_CREDENTIALS="/home/me/service-account.json"
"""
async def upload_photo_to_storage(photo: UploadFile, listing_id: str, category: str = "general") -> str:
    """Upload photo to Google Cloud Storage and return public URL"""
    try:
        # Validate file
        if not photo.content_type.startswith('image/'):
            raise ValueError("Only image files are allowed")

        if photo.size > 5_000_000:  # 5MB limit
            raise ValueError("File size too large (max 5MB)")

        # Initialize Google Cloud Storage client
        client = storage.Client()
        bucket_name = os.getenv('GOOGLE_CLOUD_STORAGE_BUCKET', 'swapwithus-images-storage')
        bucket = client.bucket(bucket_name)

        # Generate secure filename
        file_extension = photo.filename.split('.')[-1].lower() if photo.filename else 'jpg'
        if file_extension not in ['jpg', 'jpeg', 'png', 'webp']:
            file_extension = 'jpg'

        # Generate filename: category/YYYYMMDD_uuid.extension
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = str(uuid.uuid4())[:12]  # Shorter UUID (12 chars)
        blob_name = f"{category.lower()}/{listing_id}_{timestamp}_{unique_id}.{file_extension}"

        # Create blob and upload
        blob = bucket.blob(blob_name)

        # Reset file pointer to beginning
        await photo.seek(0)

        # Upload file with metadata
        blob.upload_from_file(
            photo.file,
            content_type=photo.content_type,
            timeout=30
        )

        # Note: Uniform bucket-level access is enabled, so no need for make_public()
        # The bucket should be configured for public read access at bucket level

        # Return public URL
        public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

        logger.info(f"Successfully uploaded photo: {blob_name}")
      
        return public_url

    except GoogleCloudError as e:
        logger.error(f"Google Cloud Storage error: {e}")
        raise Exception(f"Failed to upload photo: Storage service error")

    except Exception as e:
        logger.error(f"Photo upload error: {e}")
        raise Exception(f"Failed to upload photo: {str(e)}")
      

from google.cloud import storage
from datetime import timedelta, datetime
from google.auth.transport import requests as google_requests
from google.auth import compute_engine, default
import google.auth

def get_signed_url(public_url: str, expires_seconds: int = 3600) -> str:
      """Convert public URL to signed URL using IAM-based signing (works on Cloud Run)"""
      try:
          bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "swapwithus-images-storage")

          # Extract blob_name from public URL
          blob_name = public_url.split(f"storage.googleapis.com/{bucket_name}/")[1]

          # Check if running on Cloud Run (no private key available)
          if os.getenv('K_SERVICE'):
              # Use IAM signBlob API - keyless signing on Cloud Run
              from google.auth.transport import requests as google_requests
              from google.auth import compute_engine

              service_account_email = 'swapwithus-storage-service@project-8300.iam.gserviceaccount.com'

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
                  access_token=access_token
              )

              return signed_url
          else:
              # Local development - use standard signing
              client = storage.Client()
              bucket = client.bucket(bucket_name)
              blob = bucket.blob(blob_name)

              signed_url = blob.generate_signed_url(
                  expiration=timedelta(seconds=expires_seconds),
                  version="v4"
              )
              return signed_url

      except Exception as e:
          logger.error(f"CRITICAL: Failed to generate signed URL: {e}")
          # NEVER return public URLs - all images must remain private
          raise Exception(f"Cannot generate signed URL for private image: {str(e)}")
