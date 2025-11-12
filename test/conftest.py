import os 
import pytest
import pytest_asyncio
import asyncpg  
import subprocess
import app.main as main_module


# Override env vars to use Docker test database
os.environ["SWAPWITHUS_DB_USER"] = "msm"
os.environ["SWAPWITHUS_DB_PASSWORD"] = "Mk123456"
os.environ["SWAPWITHUS_DATABASE_NAME"] = "swapwithusDB"
os.environ["SWAPWITHUS_DB_HOST"] = "localhost"
os.environ["SWAPWITHUS_DB_PORT"] = "5432"

from app.database.connection import  get_db_pool



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
    main_module._db_pool = await get_db_pool()
    yield main_module._db_pool
    await main_module._db_pool.close()

