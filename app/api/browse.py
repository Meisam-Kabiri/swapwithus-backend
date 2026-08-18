import logging

from async_lru import alru_cache
from fastapi import APIRouter, HTTPException, Query, Request

from app.constants import LISTING_CATEGORIES
from app.database.connection import get_pool_from_request
from app.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter()


# from fastapi import Response
@router.get("/browse")
@limiter.limit("30/minute")
@alru_cache(maxsize=5, ttl=9 * 3600)
async def browse_homes(
    request: Request,
    category: str | None = Query(None),  # "homes", "books", "clothes", "caravans", or None for all
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
):
    """
    Browse all home listings with pagination.

    FIXED: Added pagination to prevent timeouts and crashes as listings grow.
    - Default: 20 items per page
    - Max: 100 items per page
    """
    import time

    # for now if category is NONE, neglect it and return homes only
    print(f"category received: {category}")
    if category is None:
        category = "homes"

    category = category.lower()
    if category not in LISTING_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {', '.join(LISTING_CATEGORIES)}.",
        )

    tick = time.time()
    try:
        # Calculate offset for pagination
        offset = (page - 1) * page_size

        logger.info(f"Browse {category}: page={page}, page_size={page_size}, offset={offset}")
        # Query to get paginated homes with images
        query_listings = f"""
            SELECT
                h.*,
                json_agg(
                    json_build_object(
                        'id', i.listing_id,
                        'public_url', i.public_url,
                        'cdn_url',
                            'https://cdn.swapwithus.com/{category}/' ||
                            split_part(i.public_url, 'storage.googleapis.com/swapwithus-listing-images/{category}/', 2),
                        'tag', i.tag,
                        'caption', i.caption,
                        'is_hero', i.is_hero,
                        'sort_order', i.sort_order
                    ) ORDER BY i.is_hero DESC
                ) AS images
            FROM {category} h
            INNER JOIN images i ON i.listing_id = h.listing_id
            GROUP BY h.listing_id
            ORDER BY h.created_at DESC
            LIMIT $1 OFFSET $2;
        """

        # Query to get total count
        query_count = f"SELECT COUNT(*) FROM {category};"

        async with get_pool_from_request(request).acquire() as conn:
            # Get total count for pagination metadata
            total_count = await conn.fetchval(query_count)

            # Get paginated homes
            fetched_listings = await conn.fetch(query_listings, page_size, offset)
            print(f"Fetched {len(fetched_listings)} {category} from DB")

            import math

            if not fetched_listings:
                return {
                    "category": category,
                    "listings": [],
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total_items": total_count,
                        "total_pages": math.ceil(total_count / page_size) if total_count > 0 else 0,
                        "has_next": False,
                        "has_previous": page > 1,
                    },
                }

            # Use pydantic model to return pydantic objects with camel case activated for frontend
            if category == "homes":
                from app.models.home_listing import HomeListingResponse

                listings = [
                    HomeListingResponse.model_validate(dict(lst)) for lst in fetched_listings
                ]
            elif category == "books":
                from app.models.book_listing import BookListingResponse

                listings = [
                    BookListingResponse.model_validate(dict(lst)) for lst in fetched_listings
                ]
            elif category == "clothes":
                from app.models.clothing_listing import ClothingListingResponse

                listings = [
                    ClothingListingResponse.model_validate(dict(lst)) for lst in fetched_listings
                ]
            elif category == "caravans":
                from app.models.caravan_listing import CaravanListingResponse

                listings = [
                    CaravanListingResponse.model_validate(dict(lst)) for lst in fetched_listings
                ]

            tock = time.time()
            logger.info(f"Browse homes took {tock - tick:.2f}s - returned {len(listings)} items")

            # Calculate pagination metadata
            total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
            has_next = page < total_pages
            has_previous = page > 1

            return {
                "category": category,
                "listings": listings,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_items": total_count,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_previous": has_previous,
                },
            }

    except Exception as e:
        logger.error(f"Error in browse homes: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to browse homes. Please try again.")
