"""
SwapWithUs Database Connection

SPEED + SECURITY focused architecture for swap platform:

CONNECTION METHOD - Pure asyncpg:
- asyncpg connection pool for ALL database operations
- faster than SQLAlchemy async engine
- Critical for high-frequency swap transactions
- Direct PostgreSQL protocol, minimal overhead
- Production-grade connection pooling
"""

import os
import urllib.parse

import asyncpg  # type: ignore
from fastapi import Request

# Check if running on Cloud Run (K_SERVICE env var is set by Cloud Run)
IS_CLOUD_RUN = os.getenv("K_SERVICE") is not None

# Get database credentials from environment
DB_USER = os.getenv("SWAPWITHUS_DB_USER")
DB_PASSWORD = os.getenv("SWAPWITHUS_DB_PASSWORD")
DB_NAME = os.getenv("SWAPWITHUS_DATABASE_NAME")
DB_PORT = "5432"

# Validate required env vars
if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    raise ValueError("Missing required SWAPWITHUS database environment variables")

# URL encode password to handle special characters (already validated above)
if DB_PASSWORD is None:
    raise ValueError("DB_PASSWORD cannot be None")
encoded_password = urllib.parse.quote_plus(DB_PASSWORD)

# Build connection string based on environment
if IS_CLOUD_RUN:
    # Cloud Run: Use Unix socket for Cloud SQL Proxy
    # Format: postgresql://user:pass@/dbname?host=/cloudsql/project:region:instance
    CLOUD_SQL_CONNECTION = "swapwithus-project:europe-north1:swapwithus-db"
    ASYNCPG_URL = f"postgresql://{DB_USER}:{encoded_password}@/{DB_NAME}?host=/cloudsql/{CLOUD_SQL_CONNECTION}"
    print("🌩️  Cloud Run mode: Connecting via Cloud SQL Proxy")
else:
    # Local development: Use public IP
    DB_HOST = os.getenv("SWAPWITHUS_DB_HOST")
    if not DB_HOST:
        raise ValueError("Missing SWAPWITHUS_DB_HOST for local development")
    ASYNCPG_URL = f"postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"💻 Local development mode: Connecting to {DB_HOST}")


async def create_asyncpg_pool():
    """Get asyncpg connection pool for production - optimal for swap platform"""
    return await asyncpg.create_pool(
        ASYNCPG_URL,
        min_size=0,  # Always-ready connections
        max_size=50,  # Scale with concurrent swaps
        command_timeout=60,
    )


def get_pool_from_request(request: Request) -> asyncpg.Pool:
    """Get database pool from app state (preferred for API endpoints)"""
    if not hasattr(request.app.state, 'db_pool'):
        raise RuntimeError("Database pool not initialized in app.state")
    return request.app.state.db_pool


async def get_db_conn(request: Request) -> asyncpg.Connection:
    """FastAPI dependency: acquire a connection from the app's pool for the request lifetime"""
    pool = get_pool_from_request(request)
    async with pool.acquire() as conn:
        yield conn


async def get_db_connection() -> asyncpg.Connection:
    """Get a single database connection for migrations"""
    return await asyncpg.connect(ASYNCPG_URL)


if __name__ == "__main__":
    print("Database connection module for SwapWithUs")

    import asyncio

    asyncio.run(create_asyncpg_pool())
