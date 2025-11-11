import logging
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

import asyncpg
from async_lru import alru_cache
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.database.connection import get_db_pool
from app.database.operation import DbManager
from app.middleware.auth import verify_firebase_token, verify_user_owns_resource
from app.middleware.rate_limit import custom_rate_limit_handler, limiter

#TODO: Use background tasks for image deletion/upload
#TODO: Use Dependency Injection for DB pool
#TODO: modify __init__.py for packages to make them more effective
#TODO: Add testing for all endpoints
from app.models.pydantic_models import (
    FirebaseUserIfNotExists,
    HomeListingCreate,
    ImageMetadataCollection,
    UserCreate,
    UserUpdate,
)
from app.services.gcp_image_service import (
    delete_image_from_storage,
    upload_photo_to_storage,
)
from app.utils.cdn_auth import append_token_to_url, make_urlprefix_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_db_pool: Optional[asyncpg.Pool] = None


def get_pool() -> asyncpg.Pool:
    """Get database pool with runtime check"""
    if _db_pool is None:
        raise RuntimeError("Database pool not initialized")
    return _db_pool


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
    allow_origins=[
        "http://localhost:8080",  # Local development
        "https://swapwithus.com",  # Production frontend
        "https://www.swapwithus.com",  # Production with www
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, limiter._rate_limit_exceeded_handler)
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)


# from datetime import date
# class HomeListingCreate(BaseModel):
#       # Primary key (will be generated as UUID in backend)
#       listing_id: Optional[str] = None

#       # Owner (Required)
#       owner_firebase_uid: str
#       email: Optional[str] = None
#       name: Optional[str] = None
#       profile_image: Optional[str] = None

#       # Step 1: Property Type (Optional)
#       accommodation_type: Optional[str] = None
#       property_type: Optional[str] = None

#       # Step 2: Capacity & Layout (Optional except max_guests)
#       max_guests: int
#       bedrooms: Optional[int] = None
#       # full_bathrooms: Optional[int] = None
#       # half_bathrooms: Optional[int] = None
#       size_input: Optional[str] = None
#       size_unit: Optional[str] = None
#       size_m2: Optional[int] = None
#       surroundings_type: Optional[str] = None

#       # Step 3: Location (Required: country, city; Optional: rest)
#       country: str
#       city: str
#       street_address: Optional[str] = None
#       postal_code: Optional[str] = None
#       latitude: Optional[float] = None
#       longitude: Optional[float] = None
#       privacy_radius: Optional[int] = None


#       # Step 5: House Rules
#       house_rules: Optional[List[str]] = Field(default_factory=list)
#       main_residence: Optional[bool] = None

#       # Step 6: Transport & Car Swap
#       open_to_car_swap: bool = False
#       require_car_swap_match: bool = False
#       car_details: Optional[Dict[str, Any]] = None

#       # Step 7:  Available Amenities
#       amenities: Optional[Dict[str, List[str]]] = Field(default_factory=dict)
#       accessibility_features: Optional[List[str]] = Field(default_factory=list)
#       parking_type: Optional[str] = None

#       # Step 8: Availability
#       is_flexible: Optional[bool] = None
#       available_from: Optional[date] = None
#       available_until: Optional[date] = None

#       # Step 9: Title and Description (Required: title; Optional: description)
#       title: str
#       description: Optional[str] = None

#       # Status (will default in DB)
#       status: Optional[str] = "draft"
# class imageMetadataItems(BaseModel):
#   caption: Optional[str] = None
#   tag: Optional[str] = None
#   is_hero: Optional[bool] = None
#   sort_order: Optional[int] = None

#   # Just for editing existing listing:
#   public_url: Optional[str] = None
#   cdn_url: Optional[str] = None
#   # deleted_public_urls: Optional[List[str]] = []

# class ImageMetadataCollection(BaseModel):
#       images_metadata: Optional[List[imageMetadataItems]] = []
#       deleted_public_urls: Optional[List[str]] = []

# class full_home_listing(HomeListingCreate):
#   images: Optional[List[imageMetadataItems]] = []
# class UserCreate(BaseModel):
#     owner_firebase_uid: str
#     email: str
#     name: str
#     profile_image: Optional[str] = None
#     is_email_verified: bool
# class UserUpdate(BaseModel):
#     name: Optional[str] = None
#     phone_country_code: Optional[str] = None
#     phone_number: Optional[str] = None
#     linkedin_url: Optional[str] = None
#     instagram_id: Optional[str] = None
#     facebook_id: Optional[str] = None
#     profile_image: Optional[str] = None
# class firebase_user_if_not_exists(BaseModel):
#     owner_firebase_uid: str
#     email: Optional[str] = None
#     name: Optional[str] = None
#     profile_image: Optional[str] = None

#   # FormData structure:
#   # listing: {title, bedrooms, city, ...} // JSON string

#   # images: [file1, file2, file3, ...]     // Actual image files

#   # image_0_caption: "Beautiful master bedroom"
#   # image_0_room_tag: "bedroom"
#   # image_0_is_hero: "true"
#   # image_0_sort_order: "0"

#   # image_1_caption: "Modern kitchen"
#   # image_1_room_tag: "kitchen"
#   # image_1_is_hero: "false"
#   # image_1_sort_order: "1"


@app.get("/api/health")
@limiter.limit("100/minute")
async def visit_home(request: Request):
    logger.info("Health check endpoint accessed")
    return {"message": "Welcome to SwapWithUs API!"}


@app.delete("/api/favorites/{listing_id}")
@limiter.limit("50/minute")
async def remove_favorite(request: Request, listing_id: str):
    user_id = verify_firebase_token(request)
    logger.info(f"Removing favorite for listing {listing_id}, user {user_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not listing_id:
        raise HTTPException(status_code=400, detail="listing_id is required")

    remove_favorite_query = """
  DELETE FROM favorites
  WHERE owner_firebase_uid = $1 AND listing_id = $2
  """
    async with get_pool().acquire() as conn:
        try:
            await conn.execute(remove_favorite_query, user_id, listing_id)
            return {"message": "Listing removed from favorites"}
        except Exception as e:
            logger.error(f"Error removing favorite: {e}")
            raise HTTPException(status_code=500, detail="Failed to remove favorite")


@app.post("/api/favorites")
@limiter.limit("50/minute")
async def add_favorite(request: Request):
    user_id = verify_firebase_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    listing_id = body.get("listing_id")
    logger.info(f"Adding favorite for listing {listing_id}, user {user_id}")
    if not listing_id:
        raise HTTPException(status_code=400, detail="listing_id is required")

    add_favorite_query = """
  INSERT INTO favorites (owner_firebase_uid, listing_id, created_at)
  Values ($1, $2, NOW())
  ON CONFLICT (owner_firebase_uid, listing_id) DO NOTHING
  """
    async with get_pool().acquire() as conn:
        try:
            await conn.execute(add_favorite_query, user_id, listing_id)
            return {"message": "Listing added to favorites"}
        except Exception as e:
            logger.error(f"Error adding favorite: {e}")
            raise HTTPException(status_code=500, detail="Failed to add favorite")


@app.get("/api/favorites")
@limiter.limit("50/minute")
async def get_favorites(request: Request):
    user_id = verify_firebase_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    get_favorites_query = """
    SELECT h.*,
    f.listing_id,
    i.public_url as hero_image_url
    FROM homes h
    Join favorites f ON h.listing_id = f.listing_id
    LEFT JOIN images i ON h.listing_id = i.listing_id AND i.is_hero = TRUE
    WHERE f.owner_firebase_uid = $1
    """
    async with get_pool().acquire() as conn:
        try:
            favorite_rows = await conn.fetch(get_favorites_query, user_id)
            favorites = [dict(row) for row in favorite_rows]
            for favorite in favorites:
                if favorite.get("hero_image_url"):
                    favorite["signed_url"] = append_token_to_url(
                        favorite["hero_image_url"],
                        make_urlprefix_token("https://cdn.swapwithus.com/home/"),
                    )
            return favorites
        except Exception as e:
            logger.error(f"Error fetching favorites: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch favorites")


@app.get("/api/users/me")
@limiter.limit("100/minute")
async def get_my_user_data(request: Request):
    """
    Get current user's own profile data
    UID is extracted from Firebase token, not from URL
    """
    # Extract UID from token
    uid = verify_firebase_token(request)

    query = """
        SELECT owner_firebase_uid, email, name, profile_image, phone_country_code, phone_number,
               linkedin_url, instagram_id, facebook_id, created_at, updated_at
        FROM users
        WHERE owner_firebase_uid = $1
    """
    async with get_pool().acquire() as conn:
        user_row = await conn.fetchrow(query, uid)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(user_row)


@app.get("/api/users/{uid}")
@limiter.limit("100/minute")
async def get_user_data(uid: str, request: Request):
    """
    Get another user's PUBLIC profile data (for viewing their listings)
    Returns limited public information only - no authentication required
    """
    query = """
        SELECT owner_firebase_uid, name, profile_image
        FROM users
        WHERE owner_firebase_uid = $1
    """
    async with get_pool().acquire() as conn:
        user_row = await conn.fetchrow(query, uid)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(user_row)


@app.get("/api/homes/me")
@limiter.limit("60/minute")
async def get_my_home_listings(request: Request):
    """
    Get current user's own home listings
    UID is extracted from Firebase token, not from query params
    """
    # Extract UID from token
    uid = verify_firebase_token(request)

    query_home = """
    SELECT * FROM homes WHERE owner_firebase_uid = $1
    """

    query_images = """
    SELECT
        public_url,
        'https://cdn.swapwithus.com/home/' ||
            split_part(public_url, 'storage.googleapis.com/swapwithus-listing-images/home/', 2) ||
            '?' || $3 AS signed_url,
        tag,
        caption,
        is_hero,
        sort_order
    FROM images
    WHERE
        owner_firebase_uid = $1
        AND category = 'home'
        AND listing_id = $2
    ORDER BY sort_order;
    """

    async with get_pool().acquire() as conn:
        try:
            home_rows = await conn.fetch(query_home, uid)

            listings = []
            token_prefix = make_urlprefix_token("https://cdn.swapwithus.com/home/")
            for home_row in home_rows:
                # Fetch images for this specific listing
                image_rows = await conn.fetch(
                    query_images, uid, home_row["listing_id"], token_prefix
                )
                image_rows = [dict(img) for img in image_rows]

                # Convert home row to dict and add images
                home_dict = dict(home_row)
                home_dict["images"] = image_rows
                listings.append(home_dict)

            return listings
        except Exception as e:
            logger.error(f"Error fetching user's home listings: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch listings")


@app.get("/api/homes")
@limiter.limit("60/minute")
async def get_home_listings(request: Request, owner_firebase_uid: str):

    # Verify user can only delete their own account
    verify_user_owns_resource(request, owner_firebase_uid)

    query_home = """
      SELECT * FROM homes WHERE owner_firebase_uid = $1
      """

    # query_images = """
    # SELECT public_url,  tag, caption, is_hero, sort_order
    # FROM images
    # WHERE owner_firebase_uid = $1 AND category = 'home' AND listing_id = $2
    # ORDER BY sort_order
    # """

    query_images = """
      SELECT 
          public_url,
          'https://cdn.swapwithus.com/home/' ||
              split_part(public_url, 'storage.googleapis.com/swapwithus-listing-images/home/', 2) ||
              '?' || $3 AS signed_url,
          tag,
          caption,
          is_hero,
          sort_order
      FROM images
      WHERE 
          owner_firebase_uid = $1 
          AND category = 'home' 
          AND listing_id = $2
      ORDER BY sort_order;
      """

    async with get_pool().acquire() as conn:
        try:
            home_rows = await conn.fetch(query_home, owner_firebase_uid)

            listings = []
            token_prefix = make_urlprefix_token("https://cdn.swapwithus.com/home/")
            for home_row in home_rows:
                # Fetch images for this specific listing
                image_rows = await conn.fetch(
                    query_images, owner_firebase_uid, home_row["listing_id"], token_prefix
                )
                image_rows = [dict(img) for img in image_rows]
                # for i, img in enumerate(image_rows):
                #     public_url = img['public_url']
                #     signed_url = append_token_to_url(public_url, token_prefix)
                #     image_rows[i]['signed_url'] = signed_url
                #     logger.info(signed_url)

                # Convert home row to dict
                listing = dict(home_row)

                # Add images as array
                listing["images"] = image_rows

                # Find hero image, or use first image as fallback
                hero_image = next((img for img in image_rows if img["is_hero"]), None)
                if hero_image:
                    listing["hero_image_url"] = hero_image["signed_url"]
                elif image_rows:  # ← If no hero, use first image
                    listing["hero_image_url"] = image_rows[0]["signed_url"]
                else:  # ← No images at all
                    listing["hero_image_url"] = None

                listings.append(listing)
        except Exception as e:
            logger.error(f"Error fetching listings: {e}", exc_info=True)

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
@limiter.limit("5/hour")
async def delete_home_listing(request: Request, listing_id: str):

    user_uid = verify_firebase_token(request)
    # Check if listing belongs to this user
    async with get_pool().acquire() as conn:
        listing_owner = await conn.fetchval(
            "SELECT owner_firebase_uid FROM homes WHERE listing_id = $1", listing_id
        )

        if not listing_owner:
            raise HTTPException(404, "Listing not found")

        if listing_owner != user_uid:
            raise HTTPException(403, "You don't own this listing")

    query_delete_home = """
  DELETE FROM homes WHERE listing_id = $1
  """
    query_select_images = """
  SELECT public_url FROM images WHERE listing_id = $1
  """

    async with get_pool().acquire() as conn:
        try:
            async with conn.transaction():
                urls = await conn.fetch(query_select_images, listing_id)
                await conn.execute(query_delete_home, listing_id)
                logger.info(f"Successfully deleted listing: {listing_id}")

            # Delete from storage after DB transaction
            for url in urls:
                await delete_image_from_storage(url["public_url"])
            logger.info(f"Successfully deleted images from storage for listing: {listing_id}")

            return {
                "message": "Listing deleted successfully with its corresponding images from image table and storage"
            }
        except Exception as e:
            logger.error(f"Error deleting listing: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to delete listing")


@app.post("/api/homes")
@limiter.limit("15/hour")
async def create_home_listing(
    request: Request, listing: str = Form(...), images: List[UploadFile] = File(...)
):
    """
    Create a new home listing with images.

    FIXED: Images are uploaded BEFORE database transaction to prevent:
    - Holding DB connections during slow uploads (was blocking other users)
    - Orphaned images if transaction fails
    - Transaction timeouts with many images
    """
    # Verify user is authenticated and extract UID
    user_uid = verify_firebase_token(request)

    uploaded_urls = []
    try:
        # Parse and validate input
        listing_data = HomeListingCreate.model_validate_json(listing)
        listing_data_dict = listing_data.model_dump(exclude_none=True, exclude_unset=True)

        user_data = FirebaseUserIfNotExists.model_validate_json(listing)
        user_data_dict = user_data.model_dump(exclude_none=True, exclude_unset=True)

        # Verify the token UID matches the listing owner
        if user_data_dict.get("owner_firebase_uid") != user_uid:
            raise HTTPException(403, "Cannot create listing for another user")

        metadata_collection = ImageMetadataCollection.model_validate_json(listing)
        metadata_collection_dict = metadata_collection.model_dump(exclude_none=True)
        images_metadata = metadata_collection_dict["images_metadata"]

        # Validate image count
        if len(images) > 20:
            raise HTTPException(400, "Maximum 20 images allowed per listing")

        if len(images) != len(images_metadata):
            raise HTTPException(400, "Image count doesn't match metadata count")

        generated_listing_id = str(uuid.uuid4())
        listing_data_dict["listing_id"] = generated_listing_id

        logger.info(f"Creating listing {generated_listing_id} for user {user_uid} with {len(images)} images")

        # STEP 1: Upload images FIRST (outside transaction) - IN PARALLEL
        # This prevents holding DB connections during slow uploads
        import asyncio

        upload_tasks = [
            upload_photo_to_storage(images[i], listing_id=generated_listing_id, category="home")
            for i in range(len(images))
        ]

        try:
            # Upload all images in parallel (2x-10x faster than sequential)
            uploaded_urls = await asyncio.gather(*upload_tasks)

            # Build image records for database
            image_table_records = []
            for index, metadata in enumerate(images_metadata):
                image_record = metadata.copy()
                image_record["owner_firebase_uid"] = user_data_dict.get("owner_firebase_uid")
                image_record["listing_id"] = generated_listing_id
                image_record["category"] = "home"
                image_record["public_url"] = uploaded_urls[index]
                image_table_records.append(image_record)

            logger.info(f"Successfully uploaded {len(uploaded_urls)} images in parallel")

        except Exception as upload_error:
            logger.error(f"Failed to upload images: {upload_error}")
            # Clean up any successfully uploaded images
            for url in uploaded_urls:
                if url:  # Only cleanup if upload succeeded
                    try:
                        await delete_image_from_storage(url)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup {url}: {cleanup_error}")
            raise HTTPException(500, "Failed to upload images")

        # STEP 2: Save to database (fast transaction, no blocking I/O)
        create_user_query = """
            INSERT INTO users (owner_firebase_uid, email, name, profile_image, created_at, updated_at)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (owner_firebase_uid) DO NOTHING
        """

        insert_query = """
            INSERT INTO images (
                owner_firebase_uid,
                listing_id,
                category,
                public_url,
                tag,
                caption,
                is_hero,
                sort_order
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """

        async with get_pool().acquire() as conn:
            async with conn.transaction():
                db_manager = DbManager()

                # Create user if doesn't exist
                await conn.execute(
                    create_user_query,
                    user_data_dict.get("owner_firebase_uid"),
                    user_data_dict.get("email"),
                    user_data_dict.get("name"),
                    user_data_dict.get("profile_image"),
                )

                # Create listing
                await db_manager.create_record_in_table(_db_pool, listing_data_dict, "homes")

                # Insert image records
                image_data = [
                    (
                        record["owner_firebase_uid"],
                        record["listing_id"],
                        record["category"],
                        record["public_url"],
                        record["tag"],
                        record["caption"],
                        record["is_hero"],
                        record["sort_order"],
                    )
                    for record in image_table_records
                ]
                await conn.executemany(insert_query, image_data)

        logger.info(f"Successfully created listing {generated_listing_id}")

        return JSONResponse(
            status_code=201,
            content={
                "id": str(generated_listing_id),
                "message": "Home listing created successfully",
                "image_count": len(uploaded_urls)
            },
        )

    except HTTPException:
        # Re-raise HTTP exceptions (already have proper status codes)
        raise

    except Exception as e:
        logger.error(f"Error creating listing: {type(e).__name__}: {str(e)}", exc_info=True)

        # Clean up uploaded images if database save failed
        if uploaded_urls:
            logger.info(f"Cleaning up {len(uploaded_urls)} uploaded images")
            for url in uploaded_urls:
                try:
                    await delete_image_from_storage(url)
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup image {url}: {cleanup_error}")

        # Don't expose internal error details to user
        raise HTTPException(status_code=500, detail="Failed to create listing. Please try again.")


# When: After Firebase signup (email/password, Google, or Facebook)
@app.post("/api/users")
@limiter.limit("5/hour")
async def create_user(request: Request, user: UserCreate):
    # Verify Firebase token
    user_uid = verify_firebase_token(request)

    # Verify the token UID matches the user being created
    if user.owner_firebase_uid != user_uid:
        raise HTTPException(403, "Cannot create user account for another user")

    try:
        db_manager = DbManager()
        user_dict = user.model_dump()
        await db_manager.create_record_in_table(_db_pool, user_dict, "users")
        logger.info("New user UID from DB: %s", user_dict.get("owner_firebase_uid"))
        return JSONResponse(
            status_code=201,
            content={
                "uid": user_dict.get("owner_firebase_uid"),
                "message": "User created successfully",
            },
        )
    except Exception as e:
        logger.error(f"Error creating user: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create user. Please try again.")


@app.put("/api/homes/{listing_id}")
@limiter.limit("10/minute")
async def update_home_listing(
    request: Request,
    listing_id: str,
    listing: str = Form(...),
    images: List[UploadFile] = File(default=[]),
):
    """
    Update an existing home listing.

    FIXED: Images are uploaded BEFORE database transaction to prevent
    holding DB connections during slow uploads.
    """
    # Verify user is authenticated
    user_uid = verify_firebase_token(request)

    # Check if listing belongs to this user
    async with get_pool().acquire() as conn:
        listing_owner = await conn.fetchval(
            "SELECT owner_firebase_uid FROM homes WHERE listing_id = $1", listing_id
        )

        if not listing_owner:
            raise HTTPException(404, "Listing not found")

        if listing_owner != user_uid:
            raise HTTPException(403, "You don't own this listing")

    uploaded_urls = []
    try:
        # Parse form data
        listing_data = HomeListingCreate.model_validate_json(listing)
        listing_data_dict = listing_data.model_dump(exclude_none=True)

        metadata_collection = ImageMetadataCollection.model_validate_json(listing)
        metadata_collection_dict = metadata_collection.model_dump(exclude_none=True)
        images_metadata = metadata_collection_dict["images_metadata"]
        deleted_urls = metadata_collection_dict.get("deleted_public_urls", [])

        # Validate image count
        new_images_count = sum(1 for m in images_metadata if m.get("public_url", "") == "")
        if new_images_count > 20:
            raise HTTPException(400, "Maximum 20 new images allowed")

        if len(images) != new_images_count:
            raise HTTPException(400, f"Expected {new_images_count} new images, got {len(images)}")

        logger.info(f"Updating listing {listing_id}: {new_images_count} new images, {len(deleted_urls)} to delete")

        # STEP 1: Upload NEW images FIRST (outside transaction) - IN PARALLEL
        import asyncio

        # Identify which images need uploading
        upload_tasks = []
        new_image_indices = []
        for idx, metadata in enumerate(images_metadata):
            if metadata.get("public_url", "") == "":
                new_image_indices.append(idx)
                upload_tasks.append(
                    upload_photo_to_storage(images[len(upload_tasks)], listing_id=listing_id, category="home")
                )

        try:
            # Upload all NEW images in parallel
            if upload_tasks:
                uploaded_urls = await asyncio.gather(*upload_tasks)
                logger.info(f"Successfully uploaded {len(uploaded_urls)} new images in parallel")
            else:
                uploaded_urls = []

            # Build image records for database
            image_records = []
            upload_idx = 0
            for idx, metadata in enumerate(images_metadata):
                image_record = metadata.copy()

                # If this was a new image, use the uploaded URL
                if idx in new_image_indices:
                    image_record["public_url"] = uploaded_urls[upload_idx]
                    upload_idx += 1

                # Prepare record for DB
                image_record["owner_firebase_uid"] = listing_data_dict.get("owner_firebase_uid")
                image_record["listing_id"] = listing_id
                image_record["category"] = "home"
                image_records.append(image_record)

        except Exception as upload_error:
            logger.error(f"Failed to upload images: {upload_error}")
            # Clean up any successfully uploaded images
            for url in uploaded_urls:
                if url:
                    try:
                        await delete_image_from_storage(url)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup {url}: {cleanup_error}")
            raise HTTPException(500, "Failed to upload new images")

        # STEP 2: Update database (fast transaction, no blocking I/O)
        insert_query = """
            INSERT INTO images (
                owner_firebase_uid, listing_id, category, public_url,
                tag, caption, is_hero, sort_order
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (public_url, listing_id) DO UPDATE SET
                tag = EXCLUDED.tag,
                caption = EXCLUDED.caption,
                is_hero = EXCLUDED.is_hero,
                sort_order = EXCLUDED.sort_order,
                updated_at = NOW()
        """

        async with get_pool().acquire() as conn:
            async with conn.transaction():
                db_manager = DbManager()

                # Update listing data
                await db_manager.update_record_in_table(
                    _db_pool, listing_data_dict, "homes", "listing_id", listing_id
                )

                # Delete removed images from DB
                if deleted_urls:
                    for public_url in deleted_urls:
                        await conn.execute(
                            "DELETE FROM images WHERE public_url = $1 AND listing_id = $2",
                            public_url,
                            listing_id,
                        )

                # Insert/update image records
                if image_records:
                    image_data = [
                        (
                            record["owner_firebase_uid"],
                            record["listing_id"],
                            record["category"],
                            record["public_url"],
                            record["tag"],
                            record["caption"],
                            record["is_hero"],
                            record["sort_order"],
                        )
                        for record in image_records
                    ]
                    await conn.executemany(insert_query, image_data)

        # STEP 3: Delete removed images from storage (after DB transaction succeeds)
        if deleted_urls:
            logger.info(f"Deleting {len(deleted_urls)} images from storage")
            for public_url in deleted_urls:
                try:
                    await delete_image_from_storage(public_url)
                except Exception as e:
                    logger.error(f"Failed to delete image from storage {public_url}: {e}")

        logger.info(f"Successfully updated listing {listing_id}")

        return {
            "success": True,
            "listing_id": listing_id,
            "message": "Listing updated successfully",
            "images_updated": len(image_records),
            "images_deleted": len(deleted_urls),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error updating listing: {type(e).__name__}: {str(e)}", exc_info=True)

        # Clean up uploaded images on failure
        if uploaded_urls:
            logger.info(f"Cleaning up {len(uploaded_urls)} uploaded images")
            for url in uploaded_urls:
                try:
                    await delete_image_from_storage(url)
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup image {url}: {cleanup_error}")

        raise HTTPException(status_code=500, detail="Failed to update listing. Please try again.")


# DELETE /api/users/{uid} (Delete Account)
@app.delete("/api/users/{uid}")
@limiter.limit("3/hour")
async def delete_user(request: Request, uid: str):
    # Verify user can only delete their own account
    verify_user_owns_resource(request, uid)

    try:
        async with get_pool().acquire() as conn:
            # First delete user's listings (if any)
            exist_user = await conn.fetchval(
                "SELECT 1 FROM users WHERE owner_firebase_uid = $1", uid
            )
            if not exist_user:
                logger.info(f"User {uid} not in database, skipping deletion")
                return JSONResponse(
                    status_code=200,
                    content={"message": "User not in database but deleted successfully"},
                )

            async with conn.transaction():
                # Get all images to delete from storage (simpler query)
                image_urls = await conn.fetch(
                    "SELECT public_url FROM images WHERE owner_firebase_uid = $1", uid
                )

                # Delete user (CASCADE will delete homes and images from DB)
                result = await conn.execute("DELETE FROM users WHERE owner_firebase_uid = $1", uid)
                if result == "DELETE 0":
                    raise HTTPException(status_code=404, detail="User not found")

            # Delete images from storage after DB transaction
            for image in image_urls:
                await delete_image_from_storage(image["public_url"])

            logger.info(f"Successfully deleted user and images for userID: {uid}")
            return JSONResponse(
                status_code=200, content={"message": "User and related data deleted successfully"}
            )

    except Exception as e:
        logger.error(f"Error deleting user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete user. Please try again.")


@app.patch("/api/users/{uid}")
@limiter.limit("10/minute")
async def update_user(request: Request, uid: str, user: UserUpdate):

    # Verify user can only update their own account
    verify_user_owns_resource(request, uid)
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
    logger.info(f"Updating user {uid} with fields: {list(user_dict.keys())}")
    try:
        async with get_pool().acquire() as conn:
            result = await conn.execute(
                query,
                user_dict.get("name"),
                user_dict.get("phone_country_code"),
                user_dict.get("phone_number"),
                user_dict.get("linkedin_url"),
                user_dict.get("instagram_id"),
                user_dict.get("facebook_id"),
                user_dict.get("profile_image"),
                uid,
            )
            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="User not found")
            logger.info(f"Successfully updated user: {uid}")
            return JSONResponse(status_code=200, content={"message": "User updated successfully"})
    except Exception as e:
        logger.error(f"Error updating user {uid}: {type(e).__name__}: {str(e)}", exc_info=True)


# from fastapi import Response
@app.get("/api/browse")
@limiter.limit("30/minute")
@alru_cache(maxsize=5, ttl=9 * 3600)
async def browse_homes(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)")
):
    """
    Browse all home listings with pagination.

    FIXED: Added pagination to prevent timeouts and crashes as listings grow.
    - Default: 20 items per page
    - Max: 100 items per page
    """
    import time

    tick = time.time()
    try:
        token_prefix = make_urlprefix_token("https://cdn.swapwithus.com/home/")

        # Calculate offset for pagination
        offset = (page - 1) * page_size

        logger.info(f"Browse homes: page={page}, page_size={page_size}, offset={offset}")
        # query_home = """
        #   SELECT
        #   h.*,
        #   json_agg(
        #     json_build_object(
        #       'id', i.listing_id,
        #       'public_url', i.public_url,
        #       'tag', i.tag,
        #       'caption', i.caption,
        #       'is_hero', i.is_hero
        #     ) ORDER BY i.is_hero DESC  -- <-- true comes first
        #   ) AS images
        # FROM homes h
        # INNER JOIN images i ON i.listing_id = h.listing_id
        # GROUP BY h.listing_id;

        #   """

        # Query to get paginated homes with images
        query_home = """
            SELECT
                h.*,
                json_agg(
                    json_build_object(
                        'id', i.listing_id,
                        'public_url', i.public_url,
                        'signed_url',
                            'https://cdn.swapwithus.com/home/' ||
                            split_part(i.public_url, 'storage.googleapis.com/swapwithus-listing-images/home/', 2) ||
                            '?' || $1,
                        'tag', i.tag,
                        'caption', i.caption,
                        'is_hero', i.is_hero
                    ) ORDER BY i.is_hero DESC
                ) AS images
            FROM homes h
            INNER JOIN images i ON i.listing_id = h.listing_id
            GROUP BY h.listing_id
            ORDER BY h.created_at DESC
            LIMIT $2 OFFSET $3;
        """

        # Query to get total count
        query_count = "SELECT COUNT(*) FROM homes;"

        # expiration = 3600  # 1 hour
        # cookies_value = generate_signed_cookie(expiration=3600)
        # logging.info("Generated cookies value:{cookies_value}" )
        # cookies_response = {"cdn_cookies": {
        #           "name": "Cloud-CDN-Cookie",
        #           "value": cookies_value,
        #           "expires": expiration,
        #           "domain": ".swapwithus.com"
        #       }}

        # response.set_cookie(
        #       key="Cloud-CDN-Cookie",
        #       value=cookies_value,
        #       max_age=3600,
        #       domain=".swapwithus.com",  # Works for www.swapwithus.com AND cdn.swapwithus.com
        #       secure=True,
        #       httponly=False,  # Must be False so images can use it
        #       samesite="none"
        #   )

        async with get_pool().acquire() as conn:
            # Get total count for pagination metadata
            total_count = await conn.fetchval(query_count)

            # Get paginated homes
            homes_list = await conn.fetch(query_home, token_prefix, page_size, offset)

            import json
            import math

            if not homes_list:
                return {
                    "homes": [],
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total_items": total_count,
                        "total_pages": math.ceil(total_count / page_size) if total_count > 0 else 0,
                        "has_next": False,
                        "has_previous": page > 1
                    }
                }

            # Convert to dict and parse images JSON
            homes_dict = [dict(home) for home in homes_list]

            for home in homes_dict:
                if isinstance(home.get("images"), str):
                    home["images"] = json.loads(home["images"])

            tock = time.time()
            logger.info(f"Browse homes took {tock - tick:.2f}s - returned {len(homes_dict)} items")

            # Calculate pagination metadata
            total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
            has_next = page < total_pages
            has_previous = page > 1

            return {
                "homes": homes_dict,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_items": total_count,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_previous": has_previous
                }
            }

    except Exception as e:
        logger.error(f"Error in browse homes: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to browse homes. Please try again.")


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
