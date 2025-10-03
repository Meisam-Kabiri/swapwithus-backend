"""
SwapWithUs Database Connection

SPEED + SECURITY focused architecture for swap platform:

CONNECTION METHOD - Pure asyncpg:
- asyncpg connection pool for ALL database operations
- 30-50% faster than SQLAlchemy async engine
- Critical for high-frequency swap transactions
- Direct PostgreSQL protocol, minimal overhead
- Production-grade connection pooling

QUERY BUILDING - SQLAlchemy Core only:
- SQL injection protection with parameterized queries  
- Complex query construction for swap matching logic
- Schema definitions and migrations
- NO ORM overhead, NO object mapping
- Used ONLY for building safe SQL strings

WHY NOT SQLAlchemy for connections:
- Too slow for swap platform transaction volume
- Extra abstraction layer reduces performance
- asyncpg gives direct control over PostgreSQL features

ARCHITECTURE DECISION:
Speed (asyncpg connections) + Security (SQLAlchemy Core queries) = Optimal for business growth
"""

import os 
import urllib.parse

import asyncpg
import asyncio


# Check if running on Cloud Run (K_SERVICE env var is set by Cloud Run)
IS_CLOUD_RUN = os.getenv('K_SERVICE') is not None

# Get database credentials from environment
DB_USER = os.getenv("SWAPWITHUS_DB_USER") 
DB_PASSWORD = os.getenv("SWAPWITHUS_DB_PASSWORD")
DB_NAME = os.getenv("SWAPWITHUS_DATABASE_NAME")
DB_PORT = "5432"

# Validate required env vars
if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    raise ValueError("Missing required SWAPWITHUS database environment variables")

# URL encode password to handle special characters
encoded_password = urllib.parse.quote_plus(DB_PASSWORD)

# Build connection string based on environment
if IS_CLOUD_RUN:
    # Cloud Run: Use Unix socket for Cloud SQL Proxy
    # Format: postgresql://user:pass@/dbname?host=/cloudsql/project:region:instance
    CLOUD_SQL_CONNECTION = "project-8300:europe-north1:swapwithus-postgresql"
    ASYNCPG_URL = f"postgresql://{DB_USER}:{encoded_password}@/{DB_NAME}?host=/cloudsql/{CLOUD_SQL_CONNECTION}"
    print(f"🌩️  Cloud Run mode: Connecting via Cloud SQL Proxy")
else:
    # Local development: Use public IP
    DB_HOST = os.getenv("SWAPWITHUS_DB_HOST")
    if not DB_HOST:
        raise ValueError("Missing SWAPWITHUS_DB_HOST for local development")
    ASYNCPG_URL = f"postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"💻 Local development mode: Connecting to {DB_HOST}")



# Connection functions using pure asyncpg for maximum speed
async def get_db_connection():
    """Get single asyncpg connection for simple operations"""
    return await asyncpg.connect(ASYNCPG_URL)


async def get_db_pool():
    """Get asyncpg connection pool for production - optimal for swap platform"""
    return await asyncpg.create_pool(
        ASYNCPG_URL, 
        min_size=0,      # Always-ready connections
        max_size=20,     # Scale with concurrent swaps
        command_timeout=60
    )
