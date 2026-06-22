import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

# Include API routers
from app.api.admin import router as admin_router
from app.api.browse import router as browse_router
from app.api.favorites import router as favorites_router
from app.api.listings import router as listings_router
from app.api.messaging import router as messaging_router
from app.api.reports import router as reports_router
from app.api.reviews import router as reviews_router
from app.api.swaps import router as swaps_router
from app.api.users import router as users_router
from app.api.wishlists import router as wishlists_router
from app.database.connection import create_asyncpg_pool
from app.middleware.rate_limit import custom_rate_limit_handler, limiter

# TODO: Use background tasks for image deletion/upload
# TODO: Use Dependency Injection for DB pool
# TODO: modify __init__.py for packages to make them more effective
# TODO: Add testing for all endpoints

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - Create pool once
    pool = await create_asyncpg_pool()

    # Store in app.state (for API endpoints)
    app.state.db_pool = pool

    logger.info("Database pool created at startup")

    yield  # App runs

    # Shutdown
    if app.state.db_pool:
        await app.state.db_pool.close()
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


app.include_router(listings_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(favorites_router, prefix="/api")
app.include_router(browse_router, prefix="/api")
app.include_router(messaging_router, prefix="/api")
app.include_router(swaps_router, prefix="/api")
app.include_router(reviews_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(wishlists_router, prefix="/api")


@app.get("/api/health")
@limiter.limit("100/minute")
async def visit_home(request: Request):
    logger.info("Health check endpoint accessed")
    return {"message": "Welcome to SwapWithUs API!"}


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
