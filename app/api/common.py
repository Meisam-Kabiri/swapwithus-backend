"""
Generic listing service for creating/updating/deleting listings.

Handles all listing types: books, homes, caravans, clothes, etc.
Reduces code duplication across different listing APIs.
"""
import asyncio
import logging
import uuid
from typing import List

from fastapi import HTTPException, UploadFile

from app.database.query_builder import QueryBuilder
from app.services.gcp_image_service import delete_image_from_storage, upload_photo_to_storage

logger = logging.getLogger(__name__)


async def create_listing(
    user_uid: str,
    listing_data: dict,
    user_data: dict,
    images: List[UploadFile],
    category: str,
    table_name: str,
) -> dict:
    """
    Generic listing creation handler.

    Works for any listing type: books, homes, caravans, clothes, etc.

    Args:
        user_uid: Firebase UID of the authenticated user
        listing_data: Dictionary of listing fields (from Pydantic model)
        user_data: Dictionary of user fields (email, name, profile_image)
        images: List of uploaded image files
        category: Category name for image storage ("books", "homes", etc.)
        table_name: Database table name ("books", "homes", etc.)

    Returns:
        Dictionary with listing_id and success message

    Raises:
        HTTPException: If validation fails or database operation fails
    """
    uploaded_urls = []

    try:
        # Validate image count
        if not images:
            raise HTTPException(400, "At least one image is required")

        if len(images) > 20:
            raise HTTPException(400, "Maximum 20 images allowed per listing")

        # Set owner and generate listing ID
        listing_data["owner_firebase_uid"] = user_uid
        listing_id = str(uuid.uuid4())
        listing_data["listing_id"] = listing_id

        logger.info(
            f"Creating {category} listing {listing_id} for user {user_uid} with {len(images)} images"
        )

        # STEP 1: Upload images in parallel (outside transaction)
        upload_tasks = [
            upload_photo_to_storage(img, listing_id=listing_id, category=category)
            for img in images
        ]

        try:
            uploaded_urls = await asyncio.gather(*upload_tasks)

            # Build image records for database
            image_records = []
            for i, url in enumerate(uploaded_urls):
                image_records.append({
                    "owner_firebase_uid": user_uid,
                    "listing_id": listing_id,
                    "category": category,
                    "public_url": url,
                    "cdn_url": url.replace(
                        "storage.googleapis.com/swapwithus-listing-images",
                        "cdn.swapwithus.com"
                    ),
                    "is_hero": i == 0,  # First image is hero
                    "sort_order": i,
                    "tag": None,
                    "caption": None,
                })

            logger.info(f"Successfully uploaded {len(uploaded_urls)} images in parallel")

        except Exception as upload_error:
            logger.error(f"Failed to upload images: {upload_error}")
            # Clean up any successfully uploaded images
            for url in uploaded_urls:
                if url:
                    try:
                        await delete_image_from_storage(url)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup {url}: {cleanup_error}")
            raise HTTPException(500, "Failed to upload images")

        # STEP 2: Save to database in transaction
        from app.main import get_pool

        create_user_query = """
            INSERT INTO users (owner_firebase_uid, email, name, profile_image, created_at, updated_at)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (owner_firebase_uid) DO NOTHING
        """

        insert_image_query = """
            INSERT INTO images (
                owner_firebase_uid, listing_id, category, public_url, cdn_url,
                tag, caption, is_hero, sort_order
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """

        async with get_pool().acquire() as conn:
            async with conn.transaction():
                # Create user if doesn't exist
                await conn.execute(
                    create_user_query,
                    user_uid,
                    user_data.get("email"),
                    user_data.get("name"),
                    user_data.get("profile_image"),
                )

                # Create listing - build query without executing
                insert_query, insert_values = QueryBuilder.build_insert_query(listing_data, table_name)
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
                    for record in image_records
                ]
                await conn.executemany(insert_image_query, image_data)

        logger.info(f"Successfully created {category} listing {listing_id}")

        return {
            "id": listing_id,
            "message": f"{category.title()} listing created successfully",
            "image_count": len(uploaded_urls),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            f"Error creating {category} listing: {type(e).__name__}: {str(e)}",
            exc_info=True
        )

        # Clean up uploaded images if database save failed
        if uploaded_urls:
            logger.info(f"Cleaning up {len(uploaded_urls)} uploaded images")
            for url in uploaded_urls:
                try:
                    await delete_image_from_storage(url)
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup image {url}: {cleanup_error}")

        raise HTTPException(status_code=500, detail=f"Failed to create {category} listing")
