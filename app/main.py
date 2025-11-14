import logging
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg
from async_lru import alru_cache
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

import app.database.connection as db_connection
from app.api.common import QueryBuilder
from app.database.connection import create_asyncpg_pool, get_pool
from app.middleware.auth import extract_firebase_user_uid, verify_user_owns_resource
from app.middleware.rate_limit import custom_rate_limit_handler, limiter

# TODO: Use background tasks for image deletion/upload
# TODO: Use Dependency Injection for DB pool
# TODO: modify __init__.py for packages to make them more effective
# TODO: Add testing for all endpoints
from app.models.user import UserCreate, UserUpdate
from app.services.gcp_image_service import (
    delete_image_from_storage,
)
from app.utils.cdn_auth import append_token_to_url, make_urlprefix_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db_connection._db_pool = await create_asyncpg_pool()
    logger.info("Database pool created at startup")

    yield  # App runs

    # Shutdown
    if db_connection._db_pool:
        await db_connection._db_pool.close()
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

# Include API routers
from app.api.books import router as books_router
from app.api.caravans import router as caravans_router
from app.api.clothes import router as clothes_router
from app.api.homes import router as homes_router
from app.api.users import router as users_router
from app.api.favorites import router as favorites_router

app.include_router(books_router, prefix="/api")
app.include_router(caravans_router, prefix="/api")
app.include_router(clothes_router, prefix="/api")
app.include_router(homes_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(favorites_router, prefix="/api")

@app.get("/api/health")
@limiter.limit("100/minute")
async def visit_home(request: Request):
    logger.info("Health check endpoint accessed")
    return {"message": "Welcome to SwapWithUs API!"}



# from fastapi import Response
@app.get("/api/browse")
@limiter.limit("30/minute")
@alru_cache(maxsize=5, ttl=9 * 3600)
async def browse_homes(
    request: Request,
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
                        "has_previous": page > 1,
                    },
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
                    "has_previous": has_previous,
                },
            }

    except Exception as e:
        logger.error(f"Error in browse homes: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to browse homes. Please try again.")


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

