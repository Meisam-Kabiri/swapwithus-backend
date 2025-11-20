"""
Aggregate listings API endpoint.

Returns all user's listings across all categories (homes, books, clothes, caravans).
"""

import asyncio
import json
import logging
from fastapi import Body, Form, UploadFile, File
from typing import List
from app.models.image import ImageMetadataCollection, ImageMetadataItem
from app.models.home_listing import HomeListingCreate
from app.models.book_listing import BookListingCreate
from app.models.clothing_listing import ClothingListingCreate
from app.models.caravan_listing import CaravanListingCreate

from fastapi import APIRouter, HTTPException, Request
from app.services.gcp_image_service import delete_image_from_storage, upload_photo_to_storage

from app.database.connection import get_pool
from app.database.query_builder import QueryBuilder
from app.middleware.auth import extract_firebase_user_uid, verify_user_owns_resource
from app.middleware.rate_limit import limiter
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





@router.delete("/{category}/{listing_id}")
@limiter.limit("20/hour")
async def delete_home_listing(request: Request, listing_id: str, category: str
):
    """
    Delete a home listing and all associated images.

    Removes the listing from the database and deletes all associated images
    from both the database and cloud storage. Only the owner can delete their listing.
    """
    # Authentication step - get user uid from token
    user_uid = extract_firebase_user_uid(request)
    
    

    
    category = category.lower()+"s"
    
    if category not in ["homes", "books", "clothes", "caravans"]:
        raise HTTPException(400, "Invalid category provided")
    
    # Check if listing belongs to this user
    query_delete_listing = f"""
      DELETE FROM {category} WHERE listing_id = $1
      """
    query_select_images = """
      SELECT public_url FROM images WHERE listing_id = $1
      """
    async with get_pool().acquire() as conn:
        # Authorization - verify user owns the listing
        listing_owner = await conn.fetchval(
            f"SELECT owner_firebase_uid FROM {category} WHERE listing_id = $1", listing_id
        )

        if not listing_owner:
            raise HTTPException(404, "Listing not found")

        if listing_owner != user_uid:
            raise HTTPException(403, "You don't own this listing")

     
        async with get_pool().acquire() as conn:
            try:
                async with conn.transaction():
                    urls = await conn.fetch(query_select_images, listing_id)
                    await conn.execute(query_delete_listing, listing_id)
                    logger.info(f"Successfully deleted listing: {listing_id} from table: {category}")

                # Delete from storage after DB transaction
                for url in urls:
                    await delete_image_from_storage(url["public_url"])
                logger.info(f"Successfully deleted images from storage for listing: {listing_id} in category: {category}")

                return {
                    "message": "Listing deleted successfully with its corresponding images from image table and storage"
                }
            except Exception as e:
                logger.error(f"Error deleting listing: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to delete listing")


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
    category = category.lower()+"s"
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
    for  m in list_of_metadata_items:
        if m.get("public_url") == "":
            # This is the new image
            upload_file = images[image_index]
            public_url = await upload_photo_to_storage(photo=upload_file,
                                                       listing_id=listing_id,
                                                       category=category)
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
              update_query, update_values = QueryBuilder.build_update_query(data=listings_data, table_name=category,
                                                                         where_column="listing_id",
                                                                         where_value=listing_id)
              
              await conn.execute(update_query, *update_values)
              await conn.executemany(query_delete_images, [(url, listing_id) for url in list_of_deleted_urls])
              logger.info(f"Successfully updated listing: {listing_id} in table: {category}")
            except Exception as e:
              logger.error(f"Error updating listing: {e}", exc_info=True)
              for url in uploaded_urls:
                  await delete_image_from_storage(url)
              raise HTTPException(status_code=500, detail="Failed to update listing")
              # delete the uploaded images if update failed
              
              
        # remove the images from storage
        for url in list_of_deleted_urls:
            await delete_image_from_storage(url)
        
            
          
   
   
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


