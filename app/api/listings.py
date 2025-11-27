"""
Aggregate listings API endpoint.

Returns all user's listings across all categories (homes, books, clothes, caravans).
"""

import asyncio
import json
import logging
import uuid
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.database.connection import get_pool
from app.database.query_builder import QueryBuilder
from app.middleware.auth import extract_firebase_user_uid
from app.middleware.rate_limit import limiter
from app.models.book_listing import BookListingCreate
from app.models.caravan_listing import CaravanListingCreate
from app.models.clothing_listing import ClothingListingCreate
from app.models.home_listing import HomeListingCreate
from app.models.image import ImageMetadataCollection
from app.models.user import FirebaseUserUpsert
from app.services.gcp_image_service import (delete_all_images_from_storage,
                                            delete_image_from_storage,
                                            upload_photo_to_storage)
from app.utils.cdn_auth import make_urlprefix_token

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("/me")
@limiter.limit("60/minute")
async def get_my_all_listings(request: Request):
    """
    Get all authenticated user's listings across all categories.

    Returns listings grouped by category with images aggregated as JSON arrays.
    Each listing includes signed CDN URLs for secure image access.

    Returns:
        {
            "homes": List[Dict],
            "books": List[Dict],
            "clothes": List[Dict],
            "caravans": List[Dict],
            "total": int
        }
    """
    # Authenication step - get user uid from token
    uid = extract_firebase_user_uid(request)

    async def fetch_category(category: str, token: str):
        """Fetch listings for a single category."""
        async with get_pool().acquire() as conn:
            query = QueryBuilder.build_get_listings_by_owner_id_query(category)
            logger.info(f"Fetching {category} listings for user {uid}")
            return await conn.fetch(query, uid, token)

    try:
        # Generate CDN token (valid for all categories)
        token = make_urlprefix_token("https://cdn.swapwithus.com/")

        # Fetch all categories in parallel (4 connections from pool)
        homes, books, clothes, caravans = await asyncio.gather(
            fetch_category("homes", token),
            fetch_category("books", token),
            fetch_category("clothes", token),
            fetch_category("caravans", token),
        )

        def process_rows(rows):
            """Convert database rows to dicts and parse JSON images."""
            listings = []
            for row in rows:
                listing = dict(row)
                # Parse JSON images array if it's a string
                if isinstance(listing.get("images"), str):
                    listing["images"] = json.loads(listing["images"])
                listings.append(listing)
            return listings

        # Process and return grouped by category
        result = {
            "homes": process_rows(homes),
            "books": process_rows(books),
            "clothes": process_rows(clothes),
            "caravans": process_rows(caravans),
            "total": len(homes) + len(books) + len(clothes) + len(caravans),
        }

        logger.info(f"Fetched {result['total']} listings for user {uid}")
        return result

    except Exception as e:
        logger.error(f"Error fetching user listings: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch listings")


@router.post("")
@limiter.limit("15/hour")
async def create_listing(
    request: Request,
    listing: str = Form(...),
    images: List[UploadFile] = File(...),
):
    """
    Create a new home listing with images.

    Uploads images to cloud storage in parallel, then saves listing and image
    metadata to the database. Supports up to 20 images per listing.
    """
    # Verify user is authenticated and extract UID
    user_uid = extract_firebase_user_uid(request)

    category = json.loads(listing).get("category", "").lower()
    if category not in ["homes", "books", "clothes", "caravans"]:
        raise HTTPException(400, "Invalid category provided")
      
    uploaded_urls = []
    try:
        # Parse and validate input
        if category.lower() == "homes":
            listing_data = HomeListingCreate.model_validate_json(listing)
            listing_data_dict = listing_data.model_dump(exclude_none=True, exclude_unset=True)
        elif category.lower() == "books":
            listing_data = BookListingCreate.model_validate_json(listing)
            listing_data_dict = listing_data.model_dump(exclude_none=True, exclude_unset=True)
        elif category.lower() == "clothes":
            listing_data = ClothingListingCreate.model_validate_json(listing)
            listing_data_dict = listing_data.model_dump(exclude_none=True, exclude_unset=True)
        elif category.lower() == "caravans":
            listing_data = CaravanListingCreate.model_validate_json(listing)
            listing_data_dict = listing_data.model_dump(exclude_none=True, exclude_unset=True)

        user_data = FirebaseUserUpsert.model_validate_json(listing)
        user_data_dict = user_data.model_dump(exclude_none=True, exclude_unset=True)

        metadata_collection = ImageMetadataCollection.model_validate_json(listing)
        metadata_collection_dict = metadata_collection.model_dump(exclude_none=True)
        images_metadata = metadata_collection_dict["images_metadata"]

        # Validate image count
        if len(images) > 20:
            raise HTTPException(400, "Maximum 20 images allowed per listing")

        if len(images) != len(images_metadata):
            raise HTTPException(400, "Image count doesn't match metadata count")

        for image in images:
            if image.content_type not in ["image/jpeg", "image/png"]:
                raise HTTPException(400, "Only JPEG and PNG images are allowed")

            image.file.seek(0, 2)  # Move to end of file to get size
            size = image.file.tell()
            image.file.seek(0)  # Reset to start for future reads
            if size > 5 * 1024 * 1024:  # 5MB limit
                raise HTTPException(400, "Each image must be less than 5MB")

        generated_listing_id = str(uuid.uuid4())
        listing_data_dict["listing_id"] = generated_listing_id

        logger.info(
            f"Creating listing {generated_listing_id} for user {user_uid} with {len(images)} images"
        )
    except HTTPException:
        # Re-raise HTTP exceptions (already have proper status codes)
        raise

    # STEP 1: Upload images FIRST (outside transaction) - IN PARALLEL
    # This prevents holding DB connections during slow uploads

    upload_tasks = [
        upload_photo_to_storage(images[i], listing_id=generated_listing_id, category=category)
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
            image_record["category"] = category
            public_url = uploaded_urls[index]
            image_record["public_url"] = public_url

            # Convert public URL to CDN URL
            # From: https://storage.googleapis.com/swapwithus-listing-images/homes/listing-id.jpg
            # To:   https://cdn.swapwithus.com/homes/listing-id.jpg
            blob_path = public_url.split("swapwithus-listing-images/")[
                -1
            ]  # e.g., "homes/listing_id.jpg"

            # Build CDN URL directly (category should already be plural from frontend)
            image_record["cdn_url"] = f"https://cdn.swapwithus.com/{blob_path}"

            image_table_records.append(image_record)

        logger.info(f"Successfully uploaded {len(uploaded_urls)} images in parallel")

    except Exception as upload_error:
        logger.error(f"Failed to upload images: {upload_error}")
        # Clean up any successfully uploaded images
        for url in uploaded_urls:
            if url:  # Only cleanup if upload succeeded
                try:
                    delete_image_from_storage(url)
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
            cdn_url,
            tag,
            caption,
            is_hero,
            sort_order
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """

    try:
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                # Create user if doesn't exist
                await conn.execute(
                    create_user_query,
                    user_data_dict.get("owner_firebase_uid"),
                    user_data_dict.get("email"),
                    user_data_dict.get("name"),
                    user_data_dict.get("profile_image"),
                )

                # Create listing - build query without executing
                insert_query, insert_values = QueryBuilder.build_insert_query(
                    listing_data_dict, category
                )
                await conn.execute(insert_query, *insert_values)

                # Insert image records
                image_data = [
                    (
                        record["owner_firebase_uid"],
                        record["listing_id"],
                        record["category"],
                        record["public_url"],
                        record["cdn_url"],
                        record["tag"],
                        record["caption"],
                        record["is_hero"],
                        record["sort_order"],
                    )
                    for record in image_table_records
                ]
                insert_query_image = """
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
                await conn.executemany(insert_query_image, image_data)

        logger.info(f"Successfully created listing {generated_listing_id}")

        return {
            "id": str(generated_listing_id),
            "message": "Home listing created successfully",
            "image_count": len(uploaded_urls),
        }

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
                    delete_image_from_storage(url)
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup image {url}: {cleanup_error}")

        # Don't expose internal error details to user
        raise HTTPException(status_code=500, detail="Failed to create listing. Please try again.")


@router.get("/{category}/{listing_id}")
@limiter.limit("60/minute")
async def get_listing_detail(request: Request, category: str, listing_id: str):
    """
    Get details of a single listing by ID and category.

    Returns the listing details including images with signed CDN URLs.
    """
    category = category.lower()
    if category not in ["homes", "books", "clothes", "caravans"]:
        raise HTTPException(400, "Invalid category provided")

    try:
        # Generate CDN token
        token = make_urlprefix_token("https://cdn.swapwithus.com/")

        table_name = category
        gcloud_folder_name = category
        async with get_pool().acquire() as conn:
            query = f"""
              SELECT
                    l.*,
                    '{category}' as category,
                    json_agg(
                        json_build_object(
                            'public_url', i.public_url,
                            'cdn_url', 'https://cdn.swapwithus.com/{gcloud_folder_name}/' ||
                                split_part(i.public_url, 'storage.googleapis.com/swapwithus-listing-images/{gcloud_folder_name}/', 2) ||
                                '?' || $2,
                            'tag', i.tag,
                            'caption', i.caption,
                            'is_hero', i.is_hero,
                            'sort_order', i.sort_order
                        ) ORDER BY i.sort_order
                    ) AS images
                FROM {table_name} l
                LEFT JOIN images i ON i.listing_id = l.listing_id
                WHERE l.listing_id = $1
                GROUP BY l.listing_id
                ORDER BY l.created_at DESC;
                """
            listing = await conn.fetchrow(query, listing_id, token)
            if not listing:
                raise HTTPException(404, "Listing not found")
            # convert the images JSON string to list
            listing_dict = dict(listing)
            if category == "homes":
                from app.models.home_listing import HomeListingResponse

                listing = HomeListingResponse.model_validate(listing_dict)
            elif category == "books":
                from app.models.book_listing import BookListingResponse

                listing = BookListingResponse.model_validate(listing_dict)
            elif category == "clothes":
                from app.models.clothing_listing import ClothingListingResponse

                listing = ClothingListingResponse.model_validate(listing_dict)

            elif category == "caravans":
                from app.models.caravan_listing import CaravanListingResponse

                listing = CaravanListingResponse.model_validate(listing_dict)

            return listing.model_dump(by_alias=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching listing detail: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch listing detail")


@router.delete("/{category}/{listing_id}")
@limiter.limit("15/hour")
async def delete_listing(request: Request, listing_id: str, category: str):
    """
    Delete a listing and all associated images.

    Removes the listing from the database and deletes all associated images
    from both the database and cloud storage. Only the owner can delete their listing.
    """
    # Authentication step - get user uid from token
    user_uid = extract_firebase_user_uid(request)

    category = category.lower()

    if category not in ["homes", "books", "clothes", "caravans"]:
        raise HTTPException(400, "Invalid category provided")

    async with get_pool().acquire() as conn:
        # Authorization - verify user owns the listing
        listing_owner = await conn.fetchval(
            f"SELECT owner_firebase_uid FROM {category} WHERE listing_id = $1", listing_id
        )

        if not listing_owner:
            raise HTTPException(404, "Listing not found")

        if listing_owner != user_uid:
            raise HTTPException(403, "You don't own this listing")

        try:
            async with conn.transaction():
                await conn.execute(f"DELETE FROM {category} WHERE listing_id = $1", listing_id)
                deleted_images = await conn.fetch(
                    "DELETE FROM images WHERE listing_id = $1 RETURNING *", listing_id
                )
                logger.info(f"Successfully deleted listing: {listing_id} from table: {category}")

        except Exception as e:
            logger.error(f"Error deleting listing: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to delete listing")

        # Delete from storage after DB transaction
        try:
            await delete_all_images_from_storage([url["public_url"] for url in deleted_images])
            logger.info(
                f"Successfully deleted images from storage for listing: {listing_id} in category: {category}"
            )
        except Exception as e:
            logger.error(f"Error deleting images from storage: {e}", exc_info=True)
    return {
        "message": "Listing deleted successfully with its corresponding images from image table and storage"
    }


@router.put("/{category}/{listing_id}")
@limiter.limit("15/hour")
async def update_listing(
    request: Request,
    listing_id: str,
    category: str,
    listing_data: str = Form(..., embed=True),
    images: List[UploadFile] = File(default=[]),
):
    """
    Update a listing's details.

    Allows the owner to update fields of their listing.
    The images metadata for update include a field "deleted_public_urls" which is a list of image URLs to delete.
    Also for the new images the in the metadta the the field "public_url" is sent as ""
    so this way we can find out which imges to remove, which is the same and which are new to add.
    """
    user_uid = extract_firebase_user_uid(request)
    category = category.lower()
    if category not in ["homes", "books", "clothes", "caravans"]:
        raise HTTPException(400, "Invalid category provided")

    listings_data = None
    if category == "homes":
        listing_model = HomeListingCreate.model_validate_json(listing_data)
    elif category == "books":
        listing_model = BookListingCreate.model_validate_json(listing_data)
    elif category == "clothes":
        listing_model = ClothingListingCreate.model_validate_json(listing_data)
    elif category == "caravans":
        listing_model = CaravanListingCreate.model_validate_json(listing_data)

    listings_data = listing_model.model_dump(exclude_none=True, exclude_unset=True)

    images_metadata = ImageMetadataCollection.model_validate_json(listing_data)
    images_metadata_dict = images_metadata.model_dump()
    list_of_metadata_items = images_metadata_dict.get("images_metadata", [])
    list_of_deleted_urls = images_metadata_dict.get("deleted_public_urls", [])

    # first upload the new images and get their urls:
    uploaded_urls = []
    image_index = 0
    for m in list_of_metadata_items:
        if m.get("public_url") == "":
            # This is the new image
            upload_file = images[image_index]
            public_url = await upload_photo_to_storage(
                photo=upload_file, listing_id=listing_id, category=category
            )
            uploaded_urls.append(public_url)
            image_index += 1

    # Check if listing belongs to this user

    get_owner_id_query = f"SELECT owner_firebase_uid FROM {category} WHERE listing_id = $1"
    query_delete_images = "DELETE FROM images WHERE public_url = $1 AND listing_id = $2"
    # query_add_new =
    async with get_pool().acquire() as conn:
        listing_owner = await conn.fetchval(get_owner_id_query, listing_id)

        if not listing_owner:
            raise HTTPException(404, "Listing not found")
        if listing_owner != user_uid:
            raise HTTPException(403, "You don't own this listing")

        async with conn.transaction():
            # Build update query
            try:
                update_query, update_values = QueryBuilder.build_update_query(
                    data=listings_data,
                    table_name=category,
                    where_column="listing_id",
                    where_value=listing_id,
                )

                await conn.execute(update_query, *update_values)
                await conn.executemany(
                    query_delete_images, [(url, listing_id) for url in list_of_deleted_urls]
                )
                logger.info(f"Successfully updated listing: {listing_id} in table: {category}")
            except Exception as e:
                logger.error(f"Error updating listing: {e}", exc_info=True)
                await delete_all_images_from_storage(uploaded_urls)
                raise HTTPException(status_code=500, detail="Failed to update listing")
                # delete the uploaded images if update failed

        # remove the images from storage
        await delete_all_images_from_storage(list_of_deleted_urls)


# You need to create either:
# - GET /api/listings/{listing_id} - generic endpoint for any category
# - GET /api/browse - returns all public listings (for homepage/search)
# - GET /api/browse/{listing_id} - returns one public listing


#  1. Browse listings (exists):
#   - GET /api/browse?page=1&page_size=20
#   - Returns paginated list of ALL homes for homepage/search
#   - Status: ✅ Exists (but has image URL bug)
# 2. Get single listing detail (MISSING):
#   - GET /api/listings/{listing_id}
#   - Returns ONE specific listing by ID (for listing detail page)
#   - Status: ❌ MISSING - needs to be created

# Authenticated APIs (require login):

# 3. Get my listings (exists):
#   - GET /api/listings/me
#   - Returns all user's listings across all categories
#   - Status: ✅ Exists
# 4. Create listing (exists per category):
#   - POST /api/homes, POST /api/books, etc.
#   - Status: ✅ Exists
# 5. Update listing (partially exists):
#   - PUT /api/listings/{listing_id} with category in body
#   - Status: ⚠ Backend exists but incomplete, frontend only works for homes
# 6. Delete listing (exists):
#   - DELETE /api/listings/{listing_id} with category in body
#   - Status: ✅ Exists
