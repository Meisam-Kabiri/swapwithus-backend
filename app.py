from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import asyncio
import uuid
from fastapi.middleware.cors import CORSMiddleware
from db_ops.db_manager import DbManager
from db_connection.connection_to_db import get_db_pool
    
from gcp_storage_and_api.image_upload import upload_photo_to_storage, get_signed_url, delete_image_from_storage
from gcp_storage_and_api.singning_cookies import generate_signed_cookie
from contextlib import asynccontextmanager

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global _db_pool
    _db_pool = await get_db_pool()
    logger.info("Database pool created at startup")

    yield  # App runs

    # Shutdown
    if _db_pool:
        await _db_pool.close()
        logger.info("🔒 Database pool closed")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from datetime import date
class HomeListingCreate(BaseModel):
      # Primary key (will be generated as UUID in backend)
      listing_id: Optional[str] = None

      # Owner (Required)
      owner_firebase_uid: str
      email: Optional[str] = None
      name: Optional[str] = None
      profile_image: Optional[str] = None

      # Step 1: Property Type (Optional)
      accommodation_type: Optional[str] = None
      property_type: Optional[str] = None

      # Step 2: Capacity & Layout (Optional except max_guests)
      max_guests: int
      bedrooms: Optional[int] = None
      # full_bathrooms: Optional[int] = None
      # half_bathrooms: Optional[int] = None
      size_input: Optional[str] = None
      size_unit: Optional[str] = None
      size_m2: Optional[int] = None
      surroundings_type: Optional[str] = None

      # Step 3: Location (Required: country, city; Optional: rest)
      country: str
      city: str
      street_address: Optional[str] = None
      postal_code: Optional[str] = None
      latitude: Optional[float] = None
      longitude: Optional[float] = None
      

      # Step 5: House Rules
      house_rules: Optional[List[str]] = Field(default_factory=list)
      main_residence: Optional[bool] = None

      # Step 6: Transport & Car Swap
      open_to_car_swap: bool = False
      require_car_swap_match: bool = False
      car_details: Optional[Dict[str, Any]] = None

      # Step 7:  Available Amenities
      amenities: Optional[Dict[str, List[str]]] = Field(default_factory=dict)
      accessibility_features: Optional[List[str]] = Field(default_factory=list)
      parking_type: Optional[str] = None

      # Step 8: Availability
      is_flexible: Optional[bool] = None
      available_from: Optional[date] = None
      available_until: Optional[date] = None

      # Step 9: Title and Description (Required: title; Optional: description)
      title: str
      description: Optional[str] = None

      # Status (will default in DB)
      status: Optional[str] = "draft"
class imageMetadataItems(BaseModel):
  caption: Optional[str] = None
  tag: Optional[str] = None
  is_hero: Optional[bool] = None
  sort_order: Optional[int] = None

  # Just for editing existing listing:
  public_url: Optional[str] = None
  cdn_url: Optional[str] = None
  # deleted_public_urls: Optional[List[str]] = []
  
class ImageMetadataCollection(BaseModel):
      images_metadata: Optional[List[imageMetadataItems]] = []
      deleted_public_urls: Optional[List[str]] = []

class full_home_listing(HomeListingCreate):
  images: Optional[List[imageMetadataItems]] = []
class UserCreate(BaseModel):
    owner_firebase_uid: str
    email: str
    name: str
    profile_image: Optional[str] = None
    is_email_verified: bool
class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_id: Optional[str] = None
    facebook_id: Optional[str] = None
    profile_image: Optional[str] = None
class firebase_user_if_not_exists(BaseModel):
    owner_firebase_uid: str
    email: Optional[str] = None
    name: Optional[str] = None
    profile_image: Optional[str] = None
    
  # FormData structure:
  # listing: {title, bedrooms, city, ...} // JSON string

  # images: [file1, file2, file3, ...]     // Actual image files

  # image_0_caption: "Beautiful master bedroom"
  # image_0_room_tag: "bedroom"
  # image_0_is_hero: "true"
  # image_0_sort_order: "0"

  # image_1_caption: "Modern kitchen"
  # image_1_room_tag: "kitchen"
  # image_1_is_hero: "false"
  # image_1_sort_order: "1"

@app.get("/api/homes")
async def get_home_listings(owner_firebase_uid: str):

      query_home = """
      SELECT * FROM homes WHERE owner_firebase_uid = $1
      """

      query_images = """
      SELECT public_url, cdn_url, tag, caption, is_hero, sort_order 
      FROM images 
      WHERE owner_firebase_uid = $1 AND category = 'home' AND listing_id = $2
      ORDER BY sort_order
      """

      async with _db_pool.acquire() as conn:
        try:
          home_rows = await conn.fetch(query_home, owner_firebase_uid)

          listings = []
          for home_row in home_rows:
              # Fetch images for this specific listing
              image_rows = await conn.fetch(query_images, owner_firebase_uid, home_row['listing_id'])
              image_rows = [dict(img) for img in image_rows]
              # for i, img in enumerate(image_rows):
              #     public_url = img['public_url']
              #     signed_url = get_signed_url(public_url)
              #     image_rows[i]['signed_url'] = signed_url
              #     logger.info(signed_url)

              # Convert home row to dict
              listing = dict(home_row)

              # Add images as array
              listing['images'] = image_rows

              # Find hero image, or use first image as fallback
              hero_image = next((img for img in image_rows if img['is_hero']), None)
              if hero_image:
                  listing['hero_image_url'] = hero_image['cdn_url']
              elif image_rows:  # ← If no hero, use first image
                  listing['hero_image_url'] = image_rows[0]['cdn_url']
              else:  # ← No images at all
                  listing['hero_image_url'] = None

              listings.append(listing)
        except Exception as e:
          print(f"❌ Error fetching listings: {e}")
          import traceback
          print(traceback.format_exc())
          
        finally:
          return listings  # Return array directly, not {"listings": ...}
        
          # response will look like:
          #   [
          #     {
          #       "listing_id": "uuid",
          #       "title": "Beautiful Home",
          #       "city": "Paris",
          #       "hero_image_url": "https://storage.googleapis.com/.../image1.jpg",
          #       "images": [
          #         {
          #           "cdn_url": "https://storage.googleapis.com/.../image1.jpg",
          #           "tag": "living_room",
          #           "description": "Living room",
          #           "is_hero": true,
          #           "sort_order": 0
          #         },
          #         {
          #           "cdn_url": "https://storage.googleapis.com/.../image2.jpg",
          #           "tag": "bedroom",
          #           "description": "Master bedroom",
          #           "is_hero": false,
          #           "sort_order": 1
          #         }
          #       ],
          #       ...other home fields
          #     }
#   ]


@app.delete("/api/homes/{listing_id}")
async def delete_home_listing(listing_id: str):
  query_delete_home = """
  DELETE FROM homes WHERE listing_id = $1
  """
  query_select_images = """
  SELECT public_url FROM images WHERE listing_id = $1
  """

  async with _db_pool.acquire() as conn:
    try:
      urls = await conn.fetch(query_select_images, listing_id)
      await conn.execute(query_delete_home, listing_id)
      logger.info(f"Successfully deleted listing: {listing_id}")
      for url in urls:
        delete_image_from_storage(url['public_url'])
      logger.info(f"Successfully deleted images from storage for listing: {listing_id}")

      return {"message": "Listing deleted successfully with its corresponding images from image table and storage"}
    except Exception as e:
      print(f"❌ Error deleting listing: {e}")
      import traceback
      print(traceback.format_exc())
      raise HTTPException(status_code=500, detail="Failed to delete listing")


@app.post("/api/homes")
async def create_home_listing(listing:str =  Form(...), images: List[UploadFile] = File(...)):
  try:
    # Simulate saving to database and getting an ID
    listing_data = HomeListingCreate.model_validate_json(listing)
    listing_data_dict = listing_data.model_dump(exclude_none=True)
    
    user_data = firebase_user_if_not_exists.model_validate_json(listing)
    user_data_dict = user_data.model_dump(exclude_none=True)
    
    metadata_collection = ImageMetadataCollection.model_validate_json(listing)
    metadata_collection_dict = metadata_collection.model_dump(exclude_none=True)
    images_metadata = metadata_collection_dict['images_metadata']

    # deleted_urls = metadata_collection.deleted_public_urls
    
    
    
    
    
    create_user_query = """
                        insert into users (owner_firebase_uid, email, name, profile_image, created_at, updated_at)
                        values ($1, $2, $3, $4, NOW(), NOW()) ON CONFLICT (owner_firebase_uid) DO NOTHING
                        """


    generated_listing_id = str(uuid.uuid4())
    listing_data_dict["listing_id"] = generated_listing_id
    
    print("New listing data:", listing_data_dict)
    print("Received image files:", [file.filename for file in images])
    

    db_manager = DbManager()
    await _db_pool.execute(create_user_query, user_data_dict.get("owner_firebase_uid"), user_data_dict.get("email"), user_data_dict.get("name"), user_data_dict.get("profile_image"))
    await db_manager.create_record_in_table(_db_pool, listing_data_dict, "homes")
 
    image_table_records = []
    for index, metadata in enumerate(images_metadata):
      image_url, cdn_url = await upload_photo_to_storage(images[index], listing_id = generated_listing_id, category="home")
      image_record = metadata.copy()
      image_record['owner_firebase_uid'] = listing_data_dict.get("owner_firebase_uid")
      image_record['listing_id'] = generated_listing_id
      image_record['category'] = 'home'
      image_record['public_url'] = image_url
      image_record['cdn_url'] = cdn_url
      
      image_table_records.append(image_record)
    
    
    insert_query = """
      INSERT INTO images (
          owner_firebase_uid,
          listing_id,
          category,
          public_url,
          cdn_url,
          tag,
          caption,
          is_hero,
          sort_order
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
  """
  
    # Prepare data as list of tuples
    image_data = [
        (
            record['owner_firebase_uid'],
            record['listing_id'],
            record['category'],
            record['public_url'],
            record['cdn_url'],
            record['tag'],
            record['caption'],  # caption goes into description column
            record['is_hero'],
            record['sort_order']
        )
        for record in image_table_records
    ]
    
    await _db_pool.executemany(insert_query, image_data)



    # Here you would save the listing data and images to your database/storage
    return JSONResponse(status_code=201, content={"id": str(generated_listing_id), "message": "Home listing created successfully"})
  
  except Exception as e:
          import traceback
          logger.error("=" * 50)
          logger.error("ERROR OCCURRED:")
          logger.error("Error type: %s", type(e).__name__)
          logger.error("Error message: %s", str(e))
          logger.error("=" * 50)
          logger.error("FULL TRACEBACK: %s", traceback.format_exc())
          raise HTTPException(status_code=500, detail=str(e))

# When: After Firebase signup (email/password, Google, or Facebook)
@app.post("/api/users")
async def create_user(user: UserCreate):
    try:
        db_manager = DbManager()
        user_dict = user.model_dump()
        await db_manager.create_record_in_table(_db_pool, user_dict, "users")
        logger.info("New user UID from DB: %s", user_dict.get("owner_firebase_uid"))
        return JSONResponse(status_code=201, content={"uid": user_dict.get("owner_firebase_uid"), "message": "User created successfully"})
    except Exception as e:
        import traceback
        logger.error("Error occurred while creating user: %s", str(e))
        logger.error("Error type: %s", type(e).__name__)
        logger.error("Error message: %s", str(e))
        logger.error("FULL TRACEBACK: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/homes/{listing_id}")
async def update_home_listing(
      listing_id: str,
      listing: str = Form(...),
      images: List[UploadFile] = File(default=[])
      ):
      try:
          # Parse form data
          # print("Received listing JSON:", listing)
          listing_data = HomeListingCreate.model_validate_json(listing)
          listing_data_dict = listing_data.model_dump(exclude_none=True)
          
          
          
          metadata_collection = ImageMetadataCollection.model_validate_json(listing)
          metadata_collection_dict = metadata_collection.model_dump(exclude_none=True)
          images_metadata = metadata_collection_dict['images_metadata']
          deleted_urls = metadata_collection_dict.get('deleted_public_urls', None)
                
          
          
          
          print("===================================")
          print("metadata images is :", images_metadata)

          # Extract deleted URLs from listing JSON
          deleted_urls = metadata_collection_dict.get('deleted_public_urls', [])


          # print("Updating listing:", listing_id)
          # print("Listing data:", listing_data_dict)
          # print("Image metadata:", image_metadata)
          # print("Received new image files:", len(images))
          # print("Deleted URLs:", deleted_urls)

          db_manager = DbManager()

          # 1. Update listing data in homes table
          await db_manager.update_record_in_table(
              _db_pool,
              listing_data_dict,
              "homes",
              "listing_id",
              listing_id
          )

          # 2. Delete removed images from storage and image DB
          if deleted_urls:
              for public_url in deleted_urls:
                  try:
                      await delete_image_from_storage(public_url)
                      await _db_pool.execute("DELETE FROM images WHERE public_url = $1 AND listing_id = $2", public_url, listing_id)
                  except Exception as e:
                      print(f"Error deleting image {public_url}: {e}")
                      
                      

          image_records = []
      
          # print("Public URLs from metadata:", public_urls)
          image_index = 0
          for metadata in images_metadata:
            image_record = metadata.copy()
            print("this is public url:", image_record.get('public_url', ''))
            if image_record['public_url'] == '':
              image_record['public_url'], image_record['cdn_url'] = await upload_photo_to_storage(images[image_index], listing_id=listing_id, category="home")
              image_index += 1
            image_record['owner_firebase_uid'] = listing_data_dict.get("owner_firebase_uid")
            image_record['listing_id'] = listing_id
            image_record['category'] = 'home'
            image_records.append(image_record)
          print("Final image records to insert/update:", image_records)
          
          
      
          for url in deleted_urls:
              await _db_pool.execute("DELETE FROM images WHERE public_url = $1 AND listing_id = $2", url, listing_id)

          if image_records:
              insert_query = """
                  INSERT INTO images (
                      owner_firebase_uid,
                      listing_id,
                      category,
                      public_url,
                      cdn_url,
                      tag,
                      caption,
                      is_hero,
                      sort_order
                  )
                  VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) 
                  ON CONFLICT (public_url, listing_id) DO UPDATE SET updated_at = NOW()
              """

              image_data = [
                  (
                      record['owner_firebase_uid'],
                      record['listing_id'],
                      record['category'],
                      record['public_url'],
                      record['cdn_url'],
                      record['tag'],
                      record['caption'],
                      record['is_hero'],
                      record['sort_order']
                  )
                  for record in image_records
              ]

              await _db_pool.executemany(insert_query, image_data)

          return {
              "success": True,
              "listing_id": listing_id,
              "message": "Listing updated successfully",
              "images_updated": len(image_records),
              "images_deleted": len(deleted_urls)
          }

      except Exception as e:
          print(f"Error updating listing: {e}")
          import traceback
          traceback.print_exc()
          raise HTTPException(status_code=500, detail=str(e))


# DELETE /api/users/{uid} (Delete Account)
@app.delete("/api/users/{uid}")
async def delete_user(uid: str):
    try:
        async with _db_pool.acquire() as conn:
            # First delete user's listings (if any)
            exist_user = await conn.fetchval("SELECT 1 FROM users WHERE owner_firebase_uid = $1", uid)
            if not exist_user:
                print("No listings found for user, skipping deletion of listings.")
                return JSONResponse(status_code=200, content={"message": "User not in database but deleted successfully"})
              
            # Get all images to delete from storage (simpler query)
            image_urls = await conn.fetch("SELECT public_url FROM images WHERE owner_firebase_uid = $1", uid)
            
            # Delete user (CASCADE will delete homes and images from DB)
            result = await conn.execute("DELETE FROM users WHERE owner_firebase_uid = $1", uid)
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="User not found")

            # Delete images from storage
            for image in image_urls:
                delete_image_from_storage(image['public_url'])
                
            logger.info(f"Successfully deleted user and images for userID: {uid}")
            return JSONResponse(status_code=200, content={"message": "User and related data deleted successfully"})
            
    except Exception as e:
          import traceback
          print("=" * 50)
          print("ERROR OCCURRED:")
          print(traceback.format_exc())
          print("=" * 50)
          raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/users/{uid}")
async def update_user(uid: str, user: UserUpdate):
  query = """   UPDATE users
                SET
                name = $1,
                phone_country_code = $2,
                phone_number = $3,
                linkedin_url = $4,
                instagram_id = $5,
                facebook_id = $6,
                profile_image = $7,
                updated_at = NOW()
                WHERE owner_firebase_uid = $8 """
  user_dict = user.model_dump(exclude_none=True)
  print("Updating user with data:", user_dict)
  logging.info("Updating user with data:", user_dict)
  try:
    async with _db_pool.acquire() as conn:
      result = await conn.execute(query,
                                  user_dict.get("name"),
                                  user_dict.get("phone_country_code"),
                                  user_dict.get("phone_number"),
                                  user_dict.get("linkedin_url"),
                                  user_dict.get("instagram_id"),
                                  user_dict.get("facebook_id"),
                                  user_dict.get("profile_image"),
                                  uid)
      if result == "UPDATE 0":
          raise HTTPException(status_code=404, detail="User not found")
      logging.info(f"Successfully updated user: {uid}")
      return JSONResponse(status_code=200, content={"message": "User updated successfully"})
  except Exception as e:
      import traceback
      logging.error("=" * 50)
      logging.error("ERROR OCCURRED:")
      logging.error("Error type: %s", type(e).__name__)
      logging.error("Error message: %s", str(e))
      logging.error("=" * 50)




@app.get("/browse")
async def browse_homes(response_model: List[full_home_listing] = []):
  try:
    print("Inside browse homes")
    query_home = """
      SELECT 
      h.*,
      json_agg(
        json_build_object(
          'id', i.listing_id,
          'public_url', i.public_url,
          'cdn_url', i.cdn_url,
          'tag', i.tag,
          'caption', i.caption,
          'is_hero', i.is_hero
        ) ORDER BY i.is_hero DESC  -- <-- true comes first
      ) AS images
    FROM homes h
    LEFT JOIN images i ON i.listing_id = h.listing_id
    GROUP BY h.listing_id;

      """
    
    expiration = 3600  # 1 hour
    cookies_value = generate_signed_cookie(expiration=3600)
    logging.info("Generated cookies value:", cookies_value)
    cookies_response = {"cdn_cookies": {
              "name": "Cloud-CDN-Cookie",
              "value": cookies_value,
              "expires": expiration,
              "domain": ".swapwithus.com"
          }}

    async with _db_pool.acquire() as conn:
      homes_list = await conn.fetch(query_home)
      from pprint import pprint
      import json
      # homes_list = [dict(l) for l in homes_list]
      # pprint(homes_list)
      # res = json.dumps(homes_list, indent=2, default=str)
      if not homes_list:
          return JSONResponse(status_code=404, content={"message": "No homes found"})
        
      # After fetching from DB
      homes_dict = [dict(home) for home in homes_list]

      # Parse the images JSON string for each home
      for home in homes_dict:
          if isinstance(home.get('images'), str):
              home['images'] = json.loads(home['images'])

      return {"homes": homes_dict, **cookies_response}
      # return {"homes": homes_list, **cookies_response}
    
  except Exception as e:
      import traceback
      logging.error("=" * 50)
      logging.error("ERROR OCCURRED:")
      logging.error("Error type: %s", type(e).__name__)
      logging.error("Error message: %s", str(e))
      logging.error("=" * 50)
      raise HTTPException(status_code=500, detail="Internal Server Error")


from fastapi import Response
import httpx



if __name__ == "__main__":
  
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=8000)
  
  
  
  
  # Summary Table

  # | Page     | Method         | Calls POST /api/users? | Problem?                              |
  # |----------|----------------|------------------------|---------------------------------------|
  # | Register | Email/Password | ✅ Yes                  | No                                    |
  # | Register | Google         | ✅ Yes (always)         | ⚠️ Should only create if new          |
  # | Register | Facebook       | ✅ Yes (always)         | ⚠️ Should only create if new          |
  # | Login    | Email/Password | ❌ No                   | ⚠️ Won't sync if user missing from DB |
  # | Login    | Google         | ❌ No                   | ⚠️ Won't sync if user missing from DB |
  # | Login    | Facebook       | ❌ No                   | ⚠️ Won't sync if user missing from DB |

# The Issues

#   Issue 1: Register Page Always Calls POST

#   When user clicks "Google" on register page:
#   - If NEW user → Firebase creates account → POST /api/users ✅
#   - If EXISTING user → Firebase signs them in → POST /api/users (duplicate!) → Your ON CONFLICT DO NOTHING saves you ✅

#   This is OK because you have ON CONFLICT DO NOTHING

#   ---
#   Issue 2: Login Page NEVER Calls POST

#   If user exists in Firebase but NOT in your database:
#   - They can log in ✅
#   - But your database has no record ❌
#   - Profile page will fail ❌

#   This is BAD - you need to sync

#   ---
#   The Fix: Use AuthContext (Best Solution)

#   Instead of calling POST from register/login pages, do it once in AuthContext when user loads:



  # # Simulating receiving JSON from frontend (string)
  # json_string = '''{
  #   "owner_firebase_uid": "qWMimoFaXQf5oTHEnNyD1J3L6sH2",
  #   "title": "Cozy townhouse in f Esch-Sur-Alzette",
  #   "description": "fsdf sdf sd fdfsf sdfsdfdsfsfsf",
  #   "city": "Esch-Sur-Alzette",
  #   "country": "LU",
  #   "streetAddress": "4, Boulevard des Lumieres, room number 4",
  #   "postalCode": "4369",
  #   "latitude": "49.5043904",
  #   "longitude": "5.9478725",
  #   "availableFrom": "2025-10-07",
  #   "availableUntil": "2025-10-21",
  #   "isFlexible": false,
  #   "propertyType": "townhouse",
  #   "accommodationType": "private_room",
  #   "residenceType": "primary",
  #   "bedrooms": "2",
  #   "fullBathrooms": 3,
  #   "halfBathrooms": 3,
  #   "maxGuests": "3",
  #   "sizeInput": "100",
  #   "sizeUnit": "ft2",
  #   "sizeM2": "9",
  #   "mainResidence": false,
  #   "parkingType": "driveway",
  #   "surroundingsType": "forest",
  #   "accessibilityFeatures": ["elevator"],
  #   "has_wifi": true,
  #   "has_kitchen": false,
  #   "has_washer": false,
  #   "has_heating": false,
  #   "has_linens": false,
  #   "has_towels": false,
  #   "amenities": {
  #     "kitchen": ["stove", "dishwasher"],
  #     "laundry": ["iron"],
  #     "workEntertainment": ["monitor"],
  #     "outdoor": ["outdoor_seating"],
  #     "family": ["stair_gates"],
  #     "comfortClimate": ["fans"],
  #     "safety": []
  #   },
  #   "wifiMbpsDown": "423424",
  #   "wifiMbpsUp": "3424322",
  #   "houseRules": ["pets-allowed", "no-parties"],
  #   "openToCarSwap": true,
  #   "requireCarSwapMatch": true,
  #   "carDetails": {
  #     "makeModelYear": "vovo",
  #     "transmission": "manual",
  #     "fuelType": "hybrid",
  #     "seats": "4",
  #     "minDriverAge": "25",
  #     "mileageLimit": "148",
  #     "pickupNote": "key sdsfdfs "
  #   }
  # }'''
  
  # listing_data = HomeListingCreate.model_validate_json(json_string)  # Pydantic object
  # print(listing_data.title)
  # data_dict = listing_data.model_dump(exclude_none=True)     # Python dict
  # print (**data_dict)
  
  
  
  
  
  
  
  
  
  
  
  
    
    
  # Endpoint: POST /api/users

  # When: After successful Firebase signup (email/password, Google, or Facebook)

  # Request body:
  # {
  #   "firebase_uid": "qWMimoFaXQf5oTHEnNyD1J3L6sH2",
  #   "email": "user@example.com",
  #   "name": "John Doe",
  #   "profile_image": "https://...",
  #   "isEmailVerified": true
  # }

  # SQL:
  # INSERT INTO users (firebase_uid, email, name, profile_image, isEmailVerified, created_at, updated_at)
  # VALUES (...)
  # RETURNING *;

  # ---
  # 2. Update User (called when user edits profile)

  # Endpoint: PATCH /api/users/{firebase_uid} : use patch not put

  # When: User clicks "Save Changes" on profile page

  # Request body:
  # {
  #   "name": "John Doe",
  #   "phoneCountryCode": "+352",
  #   "phoneNumber": "123456",
  #   "linkedinUrl": "...",
  #   "instagramId": "...",
  #   "facebookId": "...",
  #   "profile_image": "..."
  # }

  # SQL:
  # UPDATE users
  # SET name = $1, phoneCountryCode = $2, phoneNumber = $3, ..., updated_at = NOW()
  # WHERE firebase_uid = $10
  # RETURNING *;

  # ---
  # 3. Delete User (called when user deletes account)

  # Endpoint: DELETE /api/users/{firebase_uid}

  # When: User confirms account deletion

  # SQL:
  # -- Delete user's listings first (or use CASCADE)
  # DELETE FROM homes WHERE owner_firebase_uid = $1;

  # -- Delete user
  # DELETE FROM users WHERE firebase_uid = $1;
  
  
  #   ✅ Final API Summary:

  # 1. CREATE User - POST /api/users
  # - Field: owner_firebase_uid ✅
  # - Fields: email, name, profile_image, isEmailVerified

  # 2. UPDATE User - PATCH /api/users/{firebase_uid} ✅
  # - Uses PATCH (partial update)
  # - Fields: name, phoneCountryCode, phoneNumber, linkedinUrl, instagramId, facebookId, profile_image

  # 3. DELETE User - DELETE /api/users/{firebase_uid} ✅
  # - Deletes user and all related data

  # All field names now match your database schema!




#  cat > /tmp/firebase_auth_info.md << 'EOF'                                                                                                                                │
# │   # Firebase Authentication - What Data is Provided                                                                                                                        │
# │                                                                                                                                                                            │
# │   ## Firebase User Object Structure                                                                                                                                        │
# │   When a user signs in via Firebase (any method), you get a `User` object with these properties:                                                                           │
# │                                                                                                                                                                            │
# │   ```typescript                                                                                                                                                            │
# │   interface FirebaseUser {                                                                                                                                                 │
# │     uid: string;                    // Unique Firebase user ID (always provided)                                                                                           │
# │     email: string | null;           // User's email                                                                                                                        │
# │     emailVerified: boolean;         // Email verification status                                                                                                           │
# │     displayName: string | null;     // User's display name                                                                                                                 │
# │     photoURL: string | null;        // Profile photo URL                                                                                                                   │
# │     phoneNumber: string | null;     // Phone number (if provided)                                                                                                          │
# │     providerId: string;             // Auth provider ID                                                                                                                    │
# │     metadata: {                                                                                                                                                            │
# │       creationTime: string;                                                                                                                                                │
# │       lastSignInTime: string;                                                                                                                                              │
# │     };                                                                                                                                                                     │
# │   }                                                                                                                                                                        │
# │   ```                                                                                                                                                                      │
# │                                                                                                                                                                            │
# │   ## What Each Auth Method Provides                                                                                                                                        │
# │                                                                                                                                                                            │
# │   ### 1. Email/Password Signup                                                                                                                                             │
# │   ```typescript                                                                                                                                                            │
# │   {                                                                                                                                                                        │
# │     uid: "abc123...",              // ✅ Generated by Firebase                                                                                                              │
# │     email: "user@example.com",     // ✅ From form input                                                                                                                    │
# │     emailVerified: false,          // ❌ False initially (needs verification)                                                                                               │
# │     displayName: "John Doe",       // ✅ Set manually via updateProfile()                                                                                                   │
# │     photoURL: null,                // ❌ null (unless manually set)                                                                                                         │
# │     phoneNumber: null,             // ❌ null (unless manually added)                                                                                                       │
# │   }                                                                                                                                                                        │
# │   ```                                                                                                                                                                      │
# │   **You set manually**: firstName, lastName → combined into displayName                                                                                                    │
# │                                                                                                                                                                            │
# │   ### 2. Google OAuth Signup                                                                                                                                               │
# │   ```typescript                                                                                                                                                            │
# │   {                                                                                                                                                                        │
# │     uid: "xyz789...",              // ✅ Generated by Firebase                                                                                                              │
# │     email: "user@gmail.com",       // ✅ From Google account                                                                                                                │
# │     emailVerified: true,           // ✅ Already verified by Google                                                                                                         │
# │     displayName: "John Doe",       // ✅ From Google profile                                                                                                                │
# │     photoURL: "https://...",       // ✅ Google profile picture URL                                                                                                         │
# │     phoneNumber: null,             // ❌ Usually null (Google doesn't share)                                                                                                │
# │   }                                                                                                                                                                        │
# │   ```                                                                                                                                                                      │
# │   **Google provides**: email, displayName, photoURL, emailVerified                                                                                                         │
# │                                                                                                                                                                            │
# │   ### 3. Facebook OAuth Signup                                                                                                                                             │
# │   ```typescript                                                                                                                                                            │
# │   {                                                                                                                                                                        │
# │     uid: "fbUser123...",           // ✅ Generated by Firebase                                                                                                              │
# │     email: "user@facebook.com",    // ✅ From Facebook (if permission granted)                                                                                              │
# │     emailVerified: true,           // ✅ Already verified by Facebook                                                                                                       │
# │     displayName: "John Doe",       // ✅ From Facebook profile                                                                                                              │
# │     photoURL: "https://...",       // ✅ Facebook profile picture URL                                                                                                       │
# │     phoneNumber: null,             // ❌ null (Facebook doesn't share by default)                                                                                           │
# │   }                                                                                                                                                                        │
# │   ```                                                                                                                                                                      │
# │   **Facebook provides**: email (if permitted), displayName, photoURL, emailVerified                                                                                        │
# │   EOF                                                                                                                                                                      │
# │   cat /tmp/firebase_auth_info.md                                                                                                                                           │
# │                                                                                                                                                                            │
# │   Display Firebase auth data reference                                                                                                                                     │
# │                                                                                                                                                                            │
# │ Do you want to proceed?                                                                                                                                                    │
# │ ❯ 1. Yes                                                                                                                                                                   │
# │   2. No, and tell Claude what to do differently (esc)    




  # GET ${PYTHON_BACKEND_URL}/api/homes?owner_firebase_uid=${user.uid}
  # Expected response:
  # [
  #   {
  #     "listing_id": "uuid-here",
  #     "title": "Beautiful Home in Paris",
  #     "city": "Paris",
  #     "country": "France",
  #     "max_guests": 4,
  #     "bedrooms": 2,
  #     "full_bathrooms": 1,
  #     "status": "draft",
  #     "hero_image_url": "https://storage.googleapis.com/...",
  #     ...all other home fields
  #   },
  #   ...
  # ]

  # For Clothes:

  # GET ${PYTHON_BACKEND_URL}/api/clothes?owner_firebase_uid=${user.uid}
  # Expected response:
  # [
  #   {
  #     "listing_id": "uuid-here",
  #     "title": "Designer Jacket",
  #     "status": "published",
  #     "hero_image_url": "https://storage.googleapis.com/...",
  #     ...all other clothes fields
  #   },
  #   ...
  # ]

  # 2. Delete Listing (DELETE requests)

  # Delete Home:

  # DELETE ${PYTHON_BACKEND_URL}/api/homes/{listing_id}

  # Delete Clothes:

  # DELETE ${PYTHON_BACKEND_URL}/api/clothes/{listing_id}

  # Expected response:
  # { "message": "Listing deleted successfully" }

  # 3. What frontend needs in responses:

  # Required fields for display in profile page:

  # - listing_id (UUID) - to identify the listing
  # - title (string) - listing title
  # - city (string) - location
  # - country (string) - location
  # - status (string) - "draft" or "published"
  # - hero_image_url (string) - URL to main image (join with images table where is_hero=true)
  # - For homes: max_guests, bedrooms, full_bathrooms
  # - For clothes: whatever display fields you want

  # Should I now update the frontend to fetch both categories?
