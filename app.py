from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json
import os
import uuid
from typing import List, Optional, Dict, Any, Tuple
import firebase_admin
from connection_to_db import get_db_connection
from firebase_admin import auth
from pydantic import BaseModel
import logging
import aiohttp
from google.cloud.exceptions import GoogleCloudError
from google.cloud import storage
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

import firebase_admin
from firebase_admin import credentials

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    # Option 1: Use service account key file
    cred = credentials.Certificate("/home/meisam/.config/firebase/project-8300-firebase-adminsdk-fbsvc-e8198ebecf.json")
    firebase_admin.initialize_app(cred)




logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ListingData(BaseModel):
    title: str
    description: str
    category: str
    condition: str
    city: str
    country: str
    address: str
    available_from: Optional[str] = None
    available_until: Optional[str] = None
    value_estimate: Optional[str] = None
    preferred_swap_categories: List[str] = []
    category_data: Dict[str, Any] = {}  # Any JSON for flexibility
    owner_firebase_uid: str
    status: str = "active"


app = FastAPI()
security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust as needed for security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/listings")
async def create_listing(
    listing_data: str = Form(...),  # JSON string with listing info
    photos: List[UploadFile] = File([]),  # Photo files
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        # 1. VERIFY FIREBASE TOKEN
        firebase_token = credentials.credentials
        decoded_token = auth.verify_id_token(firebase_token)
        firebase_uid = decoded_token['uid']
        user_email = decoded_token.get('email', '')

        # 2. PARSE LISTING DATA
        listing = json.loads(listing_data)

        # 2.5. CONVERT ALL DATA TYPES FOR DATABASE
        # Convert date strings to date objects with error handling
        available_from = None
        available_until = None

        if listing.get('available_from'):
            try:
                available_from = datetime.strptime(listing['available_from'], '%Y-%m-%d').date()
            except ValueError:
                pass  # Keep as None if invalid date format

        if listing.get('available_until'):
            try:
                available_until = datetime.strptime(listing['available_until'], '%Y-%m-%d').date()
            except ValueError:
                pass  # Keep as None if invalid date format

        # Convert category_data dict to JSON string for JSONB column
        category_data_json = json.dumps(listing.get('category_data', {}))

        # Ensure preferred_swap_categories is a proper list
        preferred_categories = listing.get('preferred_swap_categories', [])

        # 3. GET/CREATE USER IN DATABASE
        conn = await get_db_connection()

        # Check if user exists, create if not
        user_row = await conn.fetchrow(
            "SELECT id FROM users WHERE firebase_uid = $1",
            firebase_uid
        )

        if not user_row:
            # Create new user
            owner_id = await conn.fetchval("""
                INSERT INTO users (firebase_uid, email, first_name, last_name) 
                VALUES ($1, $2, $3, $4) 
                RETURNING id
            """, firebase_uid, user_email,
                decoded_token.get('name', '').split(' ')[0] if decoded_token.get('name') else '',
                ' '.join(decoded_token.get('name', '').split(' ')[1:]) if decoded_token.get('name') and len(decoded_token.get('name', '').split(' ')) > 1 else ''
            )
        else:
            owner_id = user_row['id']

        # 4. UPLOAD PHOTOS TO CLOUD STORAGE
        photo_urls = []
        for photo in photos:
            # Upload to your cloud storage (AWS S3, Google Cloud Storage, etc.)
            photo_url = await upload_photo_to_storage(photo, category=listing['category'], title=listing['title'])
            photo_urls.append(photo_url)

        # 5. GEOCODE ADDRESS (Optional)
        latitude = longitude = None
        if listing.get('address'):
            try:
                latitude, longitude = await geocode_address(listing['address'])
            except:
                pass  # Geocoding failed, continue without coordinates

        # 6. SAVE LISTING TO DATABASE
        listing_id = await conn.fetchval("""
            INSERT INTO listings (
                owner_id, title, description, category, condition, 
                city, country, available_from, available_until, value_estimate,
                preferred_swap_categories, photos, category_data, 
                status, latitude, longitude, contact_name, contact_email
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
            ) RETURNING id
        """,
            owner_id,
            listing['title'],
            listing['description'],
            listing['category'],
            listing['condition'],
            listing['city'],
            listing['country'],
            available_from,
            available_until,
            listing.get('value_estimate'),
            preferred_categories,  # <- Use converted list
            photo_urls,  # Array of uploaded photo URLs
            category_data_json,  # <- Use converted JSON string
            listing.get('status', 'active'),
            latitude,
            longitude,
            listing.get('contact_name', f"{decoded_token.get('name', 'User')}"),  # Use Firebase name or default
            user_email  # Use the email from Firebase token
        )

        await conn.close()

        return {
            "success": True,
            "listing_id": listing_id,
            "message": "Listing created successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Helper functions
async def upload_photo_to_storage(photo: UploadFile, category: str = "general", title: str = None) -> str:
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
        unique_filename = f"{category.lower()}/{timestamp}_{unique_id}.{file_extension}"

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

        # Note: Uniform bucket-level access is enabled, so no need for make_public()
        # The bucket should be configured for public read access at bucket level

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

      
      
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
    # from pathlib import Path
    # import asyncio
    # from fastapi import UploadFile
    # import io
    
    # async def test_upload():
    #     # Create a mock UploadFile for testing
    #     with open("/home/meisam/Pictures/test.png", "rb") as f:
    #         file_content = f.read()
        
    #     mock_file = UploadFile(
    #         filename="test.png",
    #         file=io.BytesIO(file_content),
    #         size=len(file_content),
    #         headers={"content-type": "image/png"}
    #     )
        
    #     result = await upload_photo_to_storage(mock_file, category="books")
    #     print("Uploaded:", result)
    
    # asyncio.run(test_upload())
    
    

