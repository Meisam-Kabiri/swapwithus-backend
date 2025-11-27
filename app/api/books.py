"""
Books API endpoints

Handles CRUD operations for book listings.
"""

import logging
from typing import List

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.api.common import create_listing
from app.middleware.auth import extract_firebase_user_uid
from app.middleware.rate_limit import limiter
from app.models.book_listing import BookListingCreate
from app.models.user import FirebaseUserUpsert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["books"])


@router.post("")
@limiter.limit("15/hour")
async def create_book_listing(
    request: Request,
    listing: str = Form(...),
    images: List[UploadFile] = File(...),
):
    """
    Create a new book listing with images.

    Uses generic listing service for consistent behavior across all listing types.
    """
    # Verify user is authenticated
    user_uid = extract_firebase_user_uid(request)

    # Parse and validate input
    listing_data = BookListingCreate.model_validate_json(listing)
    user_data = FirebaseUserUpsert.model_validate_json(listing)

    # Use generic service
    return await create_listing(
        user_uid=user_uid,
        listing_data=listing_data.model_dump(exclude_none=True, exclude_unset=True),
        user_data=user_data.model_dump(exclude_none=True, exclude_unset=True),
        images=images,
        category="books",
        table_name="books",
    )


@router.get("")
@limiter.limit("60/minute")
async def get_books(request: Request, owner_firebase_uid: str):
    """Get all book listings for a specific user"""
    # TODO: Implement similar to homes endpoint
    pass


# @router.delete("/{listing_id}")
# @limiter.limit("5/hour")
# async def delete_book_listing(request: Request, listing_id: str):
#     """Delete a book listing and all associated images"""

#     try:
#       async with get_pool.acquire() as conn:
#         async with conn.transaction():
#             # verify ownership
#             extract_owner_query = "SELECT owner_firebase_uid FROM books WHERE listing_id = $1"
#             listing_owner = await conn.fetchval(extract_owner_query, listing_id)
#             verify_user_owns_resource(request, listing_owner)
#             # delete listings from books and images table (cascade delete)
#             delete_listing_query = "DELETE FROM books WHERE listing_id = $1"
#             delete_images_query = "DELETE FROM images WHERE listing_id = $1 AND category = 'books' RETURNING *"
#             await conn.execute(delete_listing_query, listing_id)
#             deleted_images = await conn.fetch(delete_images_query, listing_id)
#             logger.info(f"Deleted book listing {listing_id} and associated images.")
#             # start deleting images from GCP Storage
#             image_urls = [record["image_url"] for record in deleted_images]
#             #TODO: Better to use PoolExecutor in the delete_image_from_storage function itself
#             current_loop = asyncio.get_event_loop()
#             for url in image_urls:
#                 current_loop.run_in_executor(ThreadPoolExecutor(max_workers=5), delete_image_from_storage, url)
#             logger.info(f"Deleted {len(image_urls)} images from GCP Storage for listing {listing_id}.")
#             return {"detail": "Book listing and associated images deleted successfully."}


#     except HTTPException as http_exc:
#       raise http_exc

#     except Exception as e:
#       logger.error(f"Error in delete book listing: {type(e).__name__}: {str(e)}", exc_info=True)
#       HTTPException(status_code=500, detail="Failed to delete book listing. Please try again.")
