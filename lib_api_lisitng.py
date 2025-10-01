"""
SwapWithUs Listings API
FastAPI routes for listings management
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
import asyncpg

from ..models.listings import (
    CreateListingRequest, UpdateListingRequest, ListingResponse,
    SearchListingsRequest, SearchListingsResponse
)
from ..database.repositories.listings import ListingsRepository
from ..database.connection_to_db import get_db_pool

router = APIRouter(prefix="/listings", tags=["listings"])

# Dependency to get database pool
async def get_listings_repo() -> ListingsRepository:
    pool = await get_db_pool()
    return ListingsRepository(pool)

@router.post("/", response_model=ListingResponse)
async def create_listing(
    request: CreateListingRequest,
    listings_repo: ListingsRepository = Depends(get_listings_repo)
):
    """Create a new listing"""
    try:
        # Convert Pydantic model to dict for database
        listing_data = request.dict()

        # TODO: Get user info from authentication
        listing_data['owner_id'] = 1  # Replace with actual user ID

        # Create listing
        result = await listings_repo.create_listing(listing_data)

        # Get the full listing to return
        full_listing = await listings_repo.get_listing_by_id(result['id'])

        return ListingResponse.from_db_row(full_listing)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{listing_uuid}", response_model=ListingResponse)
async def get_listing(
    listing_uuid: str,
    listings_repo: ListingsRepository = Depends(get_listings_repo)
):
    """Get a listing by UUID"""
    listing = await listings_repo.get_listing_by_uuid(listing_uuid)

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    return ListingResponse.from_db_row(listing)

@router.get("/search", response_model=SearchListingsResponse)
async def search_listings(
    request: SearchListingsRequest = Depends(),
    listings_repo: ListingsRepository = Depends(get_listings_repo)
):
    """Search listings with filters"""
    # Convert to filters dict
    filters = request.dict(exclude_unset=True, exclude={'page', 'per_page'})

    # Database search
    db_result = await listings_repo.search_listings(
        filters, request.page, request.per_page
    )

    return SearchListingsResponse.from_db_result(db_result)

# Add other routes: update, delete, user's listings, etc.
