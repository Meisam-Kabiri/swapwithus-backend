from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import asyncio
import uuid
from fastapi.middleware.cors import CORSMiddleware
from db_ops.db_manager import DbManager
from db_connection.connection_to_db import get_db_pool
    
from gcp_storage_and_api.image_upload import upload_photo_to_storage, get_signed_url

app = FastAPI()
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
      full_bathrooms: Optional[int] = None
      half_bathrooms: Optional[int] = None
      size_input: Optional[str] = None
      size_unit: Optional[str] = None
      size_m2: Optional[int] = None

      # Step 3: Location (Required: country, city; Optional: rest)
      country: str
      city: str
      street_address: Optional[str] = None
      postal_code: Optional[str] = None
      latitude: Optional[float] = None
      longitude: Optional[float] = None

      # Step 5: Essential Features
      has_wifi: bool = False
      has_kitchen: bool = False
      has_washer: bool = False
      has_heating: bool = False
      has_linens: bool = False
      has_towels: bool = False
      wifi_mbps_down: Optional[int] = None
      wifi_mbps_up: Optional[int] = None
      surroundings_type: Optional[str] = None

      # Step 6: House Rules
      house_rules: Optional[List[str]] = Field(default_factory=list)
      main_residence: Optional[bool] = None

      # Step 7: Transport & Car Swap
      open_to_car_swap: bool = False
      require_car_swap_match: bool = False
      car_details: Optional[Dict[str, Any]] = None

      # Step 8: Practical Amenities
      amenities: Optional[Dict[str, List[str]]] = Field(default_factory=dict)
      accessibility_features: Optional[List[str]] = Field(default_factory=list)
      parking_type: Optional[str] = None

      # Step 9: Availability
      is_flexible: Optional[bool] = None
      available_from: Optional[date] = None
      available_until: Optional[date] = None

      # Step 10: Title and Description (Required: title; Optional: description)
      title: str
      description: Optional[str] = None

      # Status (will default in DB)
      status: Optional[str] = "draft"

      

class imageMetadata(BaseModel):
  caption: Optional[str] = None
  roomTag: Optional[str] = None
  isHero: Optional[bool] = False
  sortOrder: Optional[int] = 0
  
  
    
class UserCreate(BaseModel):
    owner_firebase_uid: str
    email: str
    name: str
    profileImage: Optional[str] = None
    isEmailVerified: bool 
    
  
class UserUpdate(BaseModel):
    name: Optional[str] = None
    phoneCountryCode: Optional[str] = None
    phoneNumber: Optional[str] = None
    linkedinUrl: Optional[str] = None
    instagramId: Optional[str] = None
    facebookId: Optional[str] = None
    profileImage: Optional[str] = None
    
  


class firebase_user_if_not_exists(BaseModel):
    owner_firebase_uid: str
    email: Optional[str] = None
    name: Optional[str] = None
    profileImage: Optional[str] = None
    
    

  

 


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
      pool = await get_db_pool()

      query_home = """
      SELECT * FROM homes WHERE owner_firebase_uid = $1
      """

      query_images = """
      SELECT cdn_url, tag, description, is_hero, sort_order 
      FROM images 
      WHERE owner_firebase_uid = $1 AND category = 'home' AND listing_id = $2
      ORDER BY sort_order
      """

      async with pool.acquire() as conn:
        try:
          home_rows = await conn.fetch(query_home, owner_firebase_uid)

          listings = []
          for home_row in home_rows:
              # Fetch images for this specific listing
              image_rows = await conn.fetch(query_images, owner_firebase_uid, home_row['listing_id'])
              image_rows = [dict(img) for img in image_rows]
              for i, img in enumerate(image_rows):
                  signed_url = get_signed_url(img['cdn_url'])
                  image_rows[i]['cdn_url'] = signed_url
                  print(signed_url)

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
          await conn.close() 

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
  pool = await get_db_pool()
  query = """
  DELETE FROM homes WHERE listing_id = $1
  """
  with pool.acquire() as conn:
    await conn.execute(query, listing_id)
    return {"message": "Listing deleted successfully"}

@app.post("/api/homes")
async def create_home_listing(listing:str =  Form(...), images: List[UploadFile] = File(...)):
  try:
    # Simulate saving to database and getting an ID
    listing_data = HomeListingCreate.model_validate_json(listing)
    user_data = firebase_user_if_not_exists.model_validate_json(listing)
    image_metadata_schema = imageMetadata.model_validate_json(listing)
    image_metadata = image_metadata_schema.model_dump()
    
    listing_data_dict = listing_data.model_dump(exclude_none=True)
    user_data_dict = user_data.model_dump(exclude_none=True)
    
    create_user_query = """
                        insert into users (owner_firebase_uid, email, name, profileImage, createdAt, updatedAt)
                        values ($1, $2, $3, $4, NOW(), NOW()) ON CONFLICT (owner_firebase_uid) DO NOTHING
                        """


    new_listing_id = str(uuid.uuid4())
    listing_data_dict["listing_id"] = new_listing_id
    
    print("New listing data:", listing_data_dict)
    print("Received image files:", [file.filename for file in images])
    

    pool = await get_db_pool()
    db_manager = DbManager()
    await pool.execute(create_user_query, user_data_dict.get("owner_firebase_uid"), user_data_dict.get("email"), user_data_dict.get("name"), user_data_dict.get("profileImage"))
    await db_manager.create_record_in_table(pool, listing_data_dict, "homes")
 
    image_table_records = []
    for index, image in enumerate(images):
        image_url = await upload_photo_to_storage(image, listing_id = new_listing_id, category="home")
        image_record = {
              'owner_firebase_uid': listing_data_dict.get("owner_firebase_uid"),
              'listing_id': new_listing_id,
              'category': 'home',
              'cdn_url': image_url,
              'tag': image_metadata.get(f'image_{index}_room_tag', ''),
              'caption': image_metadata.get(f'image_{index}_caption', ''),
              'is_hero': image_metadata.get(f'image_{index}_is_hero') == 'true',
              'sort_order': int(image_metadata.get(f'image_{index}_sort_order', index)),
               # 'description': image_metadata.get(f'image_{index}_description', ''),
              
          }
        image_table_records.append(image_record)
    
    insert_query = """
      INSERT INTO images (
          owner_firebase_uid,
          listing_id,
          category,
          cdn_url,
          tag,
          description,
          is_hero,
          sort_order
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
  """
  
    # Prepare data as list of tuples
    image_data = [
        (
            record['owner_firebase_uid'],
            record['listing_id'],
            record['category'],
            record['cdn_url'],
            record['tag'],
            record['caption'],  # caption goes into description column
            record['is_hero'],
            record['sort_order']
        )
        for record in image_table_records
    ]
    
    await pool.executemany(insert_query, image_data)
    await pool.close()


    # Here you would save the listing data and images to your database/storage
    return JSONResponse(status_code=201, content={"id": str(new_listing_id), "message": "Home listing created successfully"})
  
  except Exception as e:
          import traceback
          print("=" * 50)
          print("ERROR OCCURRED:")
          print("Error type:", type(e).__name__)
          print("Error message:", str(e))
          print("=" * 50)
          print("FULL TRACEBACK:")
          print(traceback.format_exc())
          print("=" * 50)
          raise HTTPException(status_code=500, detail=str(e))

   
# When: After Firebase signup (email/password, Google, or Facebook)
@app.post("/api/users")
async def create_user(user: UserCreate):
    try:
        from db_ops.db_manager import DbManager
        from db_connection.connection_to_db import get_db_pool
        pool = await get_db_pool()
        db_manager = DbManager()
        user_dict = user.model_dump()
        await db_manager.create_record_in_table(pool, user_dict, "users")
        print("New user UID from DB:", user_dict.get("owner_firebase_uid"))
        return JSONResponse(status_code=201, content={"uid": user_dict.get("owner_firebase_uid"), "message": "User created successfully"})
    except Exception as e:
        import traceback
        print("=" * 50)
        print("ERROR OCCURRED:")
        print("Error type:", type(e).__name__)
        print("Error message:", str(e))
        print("=" * 50)
        print("FULL TRACEBACK:")
        print(traceback.format_exc())
        print("=" * 50)
        raise HTTPException(status_code=500, detail=str(e))  
  



# PATCH /api/users/{uid} (Update Profile)
# When: User clicks "Save" on profile page
# URL Parameter: {uid} = Firebase user UID

@app.patch("/api/users/{uid}")
async def update_user(uid: str, user_update: UserUpdate):
    try:
        from db_ops.db_manager import DbManager
        from db_connection.connection_to_db import get_db_pool
        pool = await get_db_pool()
        db_manager = DbManager()
        update_data = user_update.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        set_clause = ', '.join([f"{key} = ${idx+1}" for idx, key in enumerate(update_data.keys())])
        values = list(update_data.values())
        values.append(uid)  # For WHERE clause

        query = f"UPDATE users SET {set_clause}, updatedAt = NOW() WHERE owner_firebase_uid = ${len(values)} RETURNING *"

        async with pool.acquire() as conn:
            updated_user = await conn.fetchrow(query, *values)
            await pool.close()
            if not updated_user:
                raise HTTPException(status_code=404, detail="User not found")
            return JSONResponse(status_code=200, content={"user": dict(updated_user), "message": "User updated successfully"})
    except Exception as e:
        import traceback
        print("=" * 50)
        print("ERROR OCCURRED:")
        print("Error type:", type(e).__name__)
        print("Error message:", str(e))
        print("=" * 50)
        print("FULL TRACEBACK:")
        print(traceback.format_exc())
        print("=" * 50)
        raise HTTPException(status_code=500, detail=str(e))  
  




# DELETE /api/users/{uid} (Delete Account)
@app.delete("/api/users/{uid}")
async def delete_user(uid: str):
    try:
        from db_ops.db_manager import DbManager
        from db_connection.connection_to_db import get_db_pool
        pool = await get_db_pool()
        db_manager = DbManager()

        async with pool.acquire() as conn:
            # First delete user's listings (if any)
            exist_user = await conn.fetchval("SELECT 1 FROM users WHERE owner_firebase_uid = $1", uid)
            if not exist_user:
                print("No listings found for user, skipping deletion of listings.")
                return JSONResponse(status_code=200, content={"message": "User not in database but deleted successfully"})
            
            # Then delete user
            result = await conn.execute("DELETE FROM users WHERE owner_firebase_uid = $1", uid)
            pool.close()
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="User not found")
            return JSONResponse(status_code=200, content={"message": "User and related data deleted successfully"})
    except Exception as e:
        import traceback
        print("=" * 50)
        print("ERROR OCCURRED:")
        print("Error type:", type(e).__name__)
        print("Error message:", str(e))
        print("=" * 50)
        print("FULL TRACEBACK:")
        print(traceback.format_exc())
        print("=" * 50)
        raise HTTPException(status_code=500, detail=str(e))

  
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
  #   "profileImage": "https://...",
  #   "isEmailVerified": true
  # }

  # SQL:
  # INSERT INTO users (firebase_uid, email, name, profileImage, isEmailVerified, createdAt, updatedAt)
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
  #   "profileImage": "..."
  # }

  # SQL:
  # UPDATE users
  # SET name = $1, phoneCountryCode = $2, phoneNumber = $3, ..., updatedAt = NOW()
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
  # - Fields: email, name, profileImage, isEmailVerified

  # 2. UPDATE User - PATCH /api/users/{firebase_uid} ✅
  # - Uses PATCH (partial update)
  # - Fields: name, phoneCountryCode, phoneNumber, linkedinUrl, instagramId, facebookId, profileImage

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
