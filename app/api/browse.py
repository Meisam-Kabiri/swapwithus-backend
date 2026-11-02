import logging

from async_lru import alru_cache
from fastapi import APIRouter, HTTPException, Query, Request

from app.constants import LISTING_CATEGORIES
from app.database.connection import get_pool_from_request
from app.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter()


def get_client_country(request: Request) -> str | None:
    """Extract client country code from cloud proxy headers (Cloudflare, GCP, AWS)."""
    return (
        request.headers.get("CF-IPCountry")
        or request.headers.get("X-Client-Geo-Country")
        or request.headers.get("CloudFront-Viewer-Country")
        or request.headers.get("X-Country-Code")
    )


# from fastapi import Response
@router.get("/browse")
@limiter.limit("30/minute")
@alru_cache(maxsize=5, ttl=9 * 3600)
async def browse_homes(
    request: Request,
    category: str | None = Query(None),  # "homes", "books", "clothes", "caravans", or None for all
    user_city: str | None = Query(None, description="User's city for location sorting"),
    user_country: str | None = Query(None, description="User's country for location sorting"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
):
    """
    Browse all listings with location ranking and pagination.
    - Tier 1: Same city
    - Tier 2: Same country (via parameter or cloud edge geo header)
    - Tier 3: Rest of world
    """
    import time

    # Handle category selection ("all" or None combines all categories in LISTING_CATEGORIES)
    selected_category = category.lower() if category else "all"

    if selected_category != "all" and selected_category not in LISTING_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be 'all' or one of: {', '.join(LISTING_CATEGORIES)}.",
        )

    tick = time.time()
    try:
        # Calculate offset for pagination
        offset = (page - 1) * page_size
        target_city = user_city.strip() if user_city else None
        target_country = user_country.strip() if user_country else get_client_country(request)

        logger.info(
            f"Browse {selected_category}: page={page}, page_size={page_size}, offset={offset}, "
            f"target_city={target_city}, target_country={target_country}"
        )

        async with get_pool_from_request(request).acquire() as conn:
            from app.models.book_listing import BookListingResponse
            from app.models.caravan_listing import CaravanListingResponse
            from app.models.clothing_listing import ClothingListingResponse
            from app.models.home_listing import HomeListingResponse

            MODEL_MAP = {
                "homes": HomeListingResponse,
                "books": BookListingResponse,
                "clothes": ClothingListingResponse,
                "caravans": CaravanListingResponse,
            }

            if selected_category == "all":
                # Combine all listing categories dynamically with uniform columns
                union_parts = [
                    f"SELECT '{cat}' AS listing_category, listing_id, title, city, country, created_at, owner_firebase_uid, to_jsonb({cat}.*) AS data FROM {cat}"
                    for cat in LISTING_CATEGORIES
                ]
                union_sql = " UNION ALL ".join(union_parts)

                query_listings = f"""
                    WITH combined AS (
                        {union_sql}
                    )
                    SELECT
                        c.listing_category,
                        c.listing_id,
                        c.title,
                        c.city,
                        c.country,
                        c.created_at,
                        c.owner_firebase_uid,
                        c.data,
                        json_agg(
                            json_build_object(
                                'id', i.listing_id,
                                'public_url', i.public_url,
                                'cdn_url',
                                    'https://cdn.swapwithus.com/' || c.listing_category || '/' ||
                                    split_part(i.public_url, 'storage.googleapis.com/swapwithus-listing-images/' || c.listing_category || '/', 2),
                                'tag', i.tag,
                                'caption', i.caption,
                                'is_hero', i.is_hero,
                                'sort_order', i.sort_order
                            ) ORDER BY i.is_hero DESC
                        ) AS images
                    FROM combined c
                    INNER JOIN images i ON i.listing_id = c.listing_id
                    GROUP BY c.listing_id, c.listing_category, c.title, c.city, c.country, c.created_at, c.owner_firebase_uid, c.data
                    ORDER BY
                        CASE
                            WHEN $1::text IS NOT NULL AND LOWER(c.city) = LOWER($1) THEN 1
                            WHEN $2::text IS NOT NULL AND (LOWER(c.country) = LOWER($2) OR UPPER(c.country) = UPPER($2)) THEN 2
                            ELSE 3
                        END ASC,
                        c.created_at DESC
                    LIMIT $3 OFFSET $4;
                """

                count_parts = [f"SELECT COUNT(*) FROM {cat}" for cat in LISTING_CATEGORIES]
                query_count = " + ".join([f"({cp})" for cp in count_parts])
                query_count_sql = f"SELECT ({query_count});"

                total_count = await conn.fetchval(query_count_sql) or 0
                fetched_listings = await conn.fetch(query_listings, target_city, target_country, page_size, offset)

                import json

                listings = []
                for lst in fetched_listings:
                    row_dict = dict(lst)
                    raw_data = row_dict.pop("data", {})
                    if isinstance(raw_data, str):
                        raw_data = json.loads(raw_data)
                    full_dict = {**raw_data, **row_dict}
                    cat_name = full_dict.get("listing_category", "homes")

                    # Parse images if returned as serialized JSON string
                    if isinstance(full_dict.get("images"), str):
                        full_dict["images"] = json.loads(full_dict["images"])

                    model_cls = MODEL_MAP.get(cat_name, HomeListingResponse)
                    validated_obj = model_cls.model_validate(full_dict)
                    obj_dict = validated_obj.model_dump(by_alias=True)
                    obj_dict["category"] = cat_name
                    listings.append(obj_dict)

            else:
                # Single category query
                query_listings = f"""
                    SELECT
                        h.*,
                        json_agg(
                            json_build_object(
                                'id', i.listing_id,
                                'public_url', i.public_url,
                                'cdn_url',
                                    'https://cdn.swapwithus.com/{selected_category}/' ||
                                    split_part(i.public_url, 'storage.googleapis.com/swapwithus-listing-images/{selected_category}/', 2),
                                'tag', i.tag,
                                'caption', i.caption,
                                'is_hero', i.is_hero,
                                'sort_order', i.sort_order
                            ) ORDER BY i.is_hero DESC
                        ) AS images
                    FROM {selected_category} h
                    INNER JOIN images i ON i.listing_id = h.listing_id
                    GROUP BY h.listing_id
                    ORDER BY
                        CASE
                            WHEN $1::text IS NOT NULL AND LOWER(h.city) = LOWER($1) THEN 1
                            WHEN $2::text IS NOT NULL AND (LOWER(h.country) = LOWER($2) OR UPPER(h.country) = UPPER($2)) THEN 2
                            ELSE 3
                        END ASC,
                        h.created_at DESC
                    LIMIT $3 OFFSET $4;
                """
                query_count_sql = f"SELECT COUNT(*) FROM {selected_category};"

                total_count = await conn.fetchval(query_count_sql) or 0
                fetched_listings = await conn.fetch(query_listings, target_city, target_country, page_size, offset)

                import json

                model_cls = MODEL_MAP.get(selected_category, HomeListingResponse)
                listings = []
                for lst in fetched_listings:
                    row_dict = dict(lst)
                    if isinstance(row_dict.get("images"), str):
                        row_dict["images"] = json.loads(row_dict["images"])
                    validated_obj = model_cls.model_validate(row_dict)
                    obj_dict = validated_obj.model_dump(by_alias=True)
                    obj_dict["category"] = selected_category
                    listings.append(obj_dict)

            import math

            tock = time.time()
            logger.info(f"Browse {selected_category} took {tock - tick:.2f}s - returned {len(listings)} items")

            total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
            has_next = page < total_pages
            has_previous = page > 1

            return {
                "category": selected_category,
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
        logger.error(f"Error in browse: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to browse listings. Please try again.")
