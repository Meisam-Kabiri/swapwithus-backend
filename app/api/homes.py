import logging
import uuid
from typing import List

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    logger,
)
from fastapi.responses import JSONResponse
import asyncio

from app.api.common import QueryBuilder
from app.database.connection import get_pool 
from app.main import get_pool
from app.middleware.auth import verify_firebase_token, verify_user_owns_resource
from app.middleware.rate_limit import limiter
from app.models.home_listing import HomeListingCreate
from app.models.image import ImageMetadataCollection
from app.models.user import FirebaseUserUpsert, UserCreate
from app.services.gcp_image_service import (
    delete_image_from_storage,
    upload_photo_to_storage,
)
from app.utils.cdn_auth import make_urlprefix_token

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/homes", tags=["homes"])


@router.get("/me")
@limiter.limit("60/minute")
async def get_my_home_listings(request: Request):
    """
    Get authenticated user's home listings with signed image URLs.

    Returns all home listings owned by the authenticated user,
    including images with CDN-signed URLs for secure access.
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


@router.get("")
@limiter.limit("60/minute")
async def get_home_listings(request: Request, owner_firebase_uid: str):
    """
    Get home listings for a specific user by Firebase UID.

    Returns all home listings owned by the specified user with signed image URLs,
    hero image selection, and complete listing details.
    """
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


@router.delete("{listing_id}")
@limiter.limit("5/hour")
async def delete_home_listing(request: Request, listing_id: str):
    """
    Delete a home listing and all associated images.

    Removes the listing from the database and deletes all associated images
    from both the database and cloud storage. Only the owner can delete their listing.
    """
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


@router.post("")
@limiter.limit("15/hour")
async def create_home_listing(
    request: Request, listing: str = Form(...), images: List[UploadFile] = File(...)
):
    """
    Create a new home listing with images.

    Uploads images to cloud storage in parallel, then saves listing and image
    metadata to the database. Supports up to 20 images per listing.
    """
    # Verify user is authenticated and extract UID
    user_uid = verify_firebase_token(request)

    uploaded_urls = []
    try:
        # Parse and validate input
        listing_data = HomeListingCreate.model_validate_json(listing)
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

        generated_listing_id = str(uuid.uuid4())
        listing_data_dict["listing_id"] = generated_listing_id

        logger.info(
            f"Creating listing {generated_listing_id} for user {user_uid} with {len(images)} images"
        )

        # STEP 1: Upload images FIRST (outside transaction) - IN PARALLEL
        # This prevents holding DB connections during slow uploads

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
                    listing_data_dict, "homes"
                )
                await conn.execute(insert_query, *insert_values)

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
                "image_count": len(uploaded_urls),
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


@router.put("/{listing_id}")
@limiter.limit("10/minute")
async def update_home_listing(
    request: Request,
    listing_id: str,
    listing: str = Form(...),
    images: List[UploadFile] = File(default=[]),
):
    """
    Update an existing home listing.

    Supports updating listing details, adding new images, removing old images,
    and modifying image metadata. Only the owner can update their listing.
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

        logger.info(
            f"Updating listing {listing_id}: {new_images_count} new images, {len(deleted_urls)} to delete"
        )

        # STEP 1: Upload NEW images FIRST (outside transaction) - IN PARALLEL
        

        # Identify which images need uploading
        upload_tasks = []
        new_image_indices = []
        for idx, metadata in enumerate(images_metadata):
            if metadata.get("public_url", "") == "":
                new_image_indices.append(idx)
                upload_tasks.append(
                    upload_photo_to_storage(
                        images[len(upload_tasks)], listing_id=listing_id, category="home"
                    )
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
                # Update listing data - build query without executing
                update_query, update_values = QueryBuilder.build_update_query(
                    listing_data_dict, "homes", "listing_id", listing_id
                )
                await conn.execute(update_query, *update_values)

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
