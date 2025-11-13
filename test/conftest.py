import os
import subprocess
import sys

# Override env vars to use Docker test database BEFORE any imports
os.environ["SWAPWITHUS_DB_USER"] = "msm"
os.environ["SWAPWITHUS_DB_PASSWORD"] = "Mk123456"
os.environ["SWAPWITHUS_DATABASE_NAME"] = "swapwithusDB"
os.environ["SWAPWITHUS_DB_HOST"] = "localhost"
os.environ["SWAPWITHUS_DB_PORT"] = "5432"

import pytest
import pytest_asyncio

import app.database.connection as db_connection
from app.database.connection import ASYNCPG_URL, create_asyncpg_pool

# SAFETY CHECK: Prevent tests from connecting to production GCP database
PRODUCTION_IP = "35.228.209.98"
if PRODUCTION_IP in ASYNCPG_URL:
    print("❌ FATAL: Tests are trying to connect to PRODUCTION database!")
    print(f"❌ Connection string: {ASYNCPG_URL}")
    sys.exit(1)

if "localhost" not in ASYNCPG_URL and "127.0.0.1" not in ASYNCPG_URL:
    print(f"❌ FATAL: Tests must connect to localhost, not: {ASYNCPG_URL}")
    sys.exit(1)

print(f"✅ Tests connecting to: {ASYNCPG_URL}")


@pytest.fixture(scope="session", autouse=True)
def docker_compose():
    # Start docker-compose
    subprocess.run(["docker", "compose", "up", "-d"], check=True)

    import time

    time.sleep(1)  # Wait for the database to be ready
    yield  # tests run after this point

    # Teardown: stop docker-compose
    subprocess.run(["docker", "compose", "down"], check=True)


@pytest_asyncio.fixture(scope="function")
async def create_db_pool():
    db_connection._db_pool = await create_asyncpg_pool()
    yield db_connection._db_pool

    await db_connection._db_pool.close()
