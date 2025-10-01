def my_test_decorator(func):
    def wrapper(*args, **kwargs):
        print("Before function call")
        result = func(*args, **kwargs)
        print("After function call")
        return result
    return wrapper
  
  
if __name__ == "__main__":
    @my_test_decorator
    def say_hello(name):
        print(f"Hello, {name}!")
    
    say_hello("World")
    
    a = 1
    b = 0
    try: 
      c = a/b
    except Exception as e:
      print("Error:", e)
      # raise e
    finally:
      print("In finally block")
      
    print("End of test")
    
    
    
    
    
    
  async def upload_photo_to_storage(photo: UploadFile) -> str:
    """Upload photo to Google Cloud Storage and return public URL"""
    try:
        # Validate file
        if not photo.content_type.startswith('image/'):
            raise ValueError("Only image files are allowed")

        if photo.size > 5_000_000:  # 5MB limit
            raise ValueError("File size too large (max 5MB)")

        # Initialize Google Cloud Storage client
        client = storage.Client()
        bucket_name = os.getenv('GOOGLE_CLOUD_STORAGE_BUCKET', 'swapwithus-photos')
        bucket = client.bucket(bucket_name)

        # Generate secure filename
        file_extension = photo.filename.split('.')[-1].lower() if photo.filename else 'jpg'
        if file_extension not in ['jpg', 'jpeg', 'png', 'webp']:
            file_extension = 'jpg'

        # Create unique filename: listings/uuid.extension
        unique_filename = f"listings/{uuid.uuid4()}.{file_extension}"

        # Create blob and upload
        blob = bucket.blob(unique_filename)

        # Reset file pointer to beginning
        await photo.seek(0)

        # Upload file with metadata
        blob.upload_from_file(
            photo.file,
            content_type=photo.content_type,
            timeout=30
        )

        # Make blob publicly readable
        blob.make_public()

        # Return public URL
        public_url = f"https://storage.googleapis.com/{bucket_name}/{unique_filename}"

        logger.info(f"Successfully uploaded photo: {unique_filename}")
        return public_url

    except GoogleCloudError as e:
        logger.error(f"Google Cloud Storage error: {e}")
        raise Exception(f"Failed to upload photo: Storage service error")

    except Exception as e:
        logger.error(f"Photo upload error: {e}")
        raise Exception(f"Failed to upload photo: {str(e)}")


2. Google Geocoding API

import aiohttp
import os
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

async def geocode_address(address: str) -> Tuple[Optional[float], Optional[float]]:
    """Convert address to coordinates using Google Geocoding API"""
    try:
        if not address or not address.strip():
            return None, None

        # Get API key from environment
        api_key = os.getenv('GOOGLE_GEOCODING_API_KEY')
        if not api_key:
            logger.warning("Google Geocoding API key not found")
            return None, None

        # Prepare API request
        base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'address': address.strip(),
            'key': api_key,
            'region': 'US'  # Optional: bias results to a specific region
        }

        # Make async HTTP request
        timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(base_url, params=params) as response:
                if response.status != 200:
                    logger.error(f"Geocoding API returned status {response.status}")
                    return None, None

                data = await response.json()

        # Parse response
        if data.get('status') == 'OK' and data.get('results'):
            location = data['results'][0]['geometry']['location']
            latitude = location['lat']
            longitude = location['lng']

            logger.info(f"Successfully geocoded address: {address}")
            return latitude, longitude

        elif data.get('status') == 'ZERO_RESULTS':
            logger.warning(f"No results found for address: {address}")
            return None, None

        else:
            logger.error(f"Geocoding failed: {data.get('status')} - {data.get('error_message', 'Unknown error')}")
            return None, None

    except aiohttp.ClientError as e:
        logger.error(f"HTTP request error during geocoding: {e}")
        return None, None

    except Exception as e:
        logger.error(f"Geocoding error: {e}")
        return None, None

