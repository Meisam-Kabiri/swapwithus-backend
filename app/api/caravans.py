"""
Caravans API endpoints

Handles CRUD operations for caravan listings.
"""
import logging
from typing import List

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.api.common import create_listing
from app.middleware.auth import verify_firebase_token
from app.middleware.rate_limit import limiter
from app.models.caravan_listing import CaravanListingCreate
from app.models.user import FirebaseUserUpsert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/caravans", tags=["caravans"])


@router.post("")
@limiter.limit("15/hour")
async def create_caravan_listing(
    request: Request,
    listing: str = Form(...),
    images: List[UploadFile] = File(...),
):
    """
    Create a new caravan listing with images.

    Uses generic listing service for consistent behavior across all listing types.
    """
    # Verify user is authenticated
    user_uid = verify_firebase_token(request)

    # Parse and validate input
    listing_data = CaravanListingCreate.model_validate_json(listing)
    user_data = FirebaseUserUpsert.model_validate_json(listing)

    # Use generic service
    return await create_listing(
        user_uid=user_uid,
        listing_data=listing_data.model_dump(exclude_none=True, exclude_unset=True),
        user_data=user_data.model_dump(exclude_none=True, exclude_unset=True),
        images=images,
        category="caravans",
        table_name="caravans",
    )


@router.get("")
@limiter.limit("60/minute")
async def get_caravans(request: Request, owner_firebase_uid: str):
    """Get all caravan listings for a specific user"""
    # TODO: Implement similar to homes endpoint
    pass


@router.delete("/{listing_id}")
@limiter.limit("5/hour")
async def delete_caravan_listing(request: Request, listing_id: str):
    """Delete a caravan listing and all associated images"""
    # TODO: Implement similar to homes endpoint
    pass
