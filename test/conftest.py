import os
import subprocess
import sys
from unittest.mock import patch

from google.cloud import storage

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


# no need to mock the whole method, only we can mock the returnn using return_value= ()
@pytest.fixture(scope="session", autouse=True)
def mock_optimize_images():
    with patch(
        "app.services.gcp_image_service.optimize_image",
        side_effect=lambda file_content, max_width, quality: (file_content, "image/jpeg"),
    ) as mock_func:
        yield mock_func


@pytest.fixture(scope="session", autouse=False)
def fake_upload_images_to_gcp():
    """Fixture to mock GCP image upload during tests"""
    import uuid
    from unittest.mock import AsyncMock

    with patch("app.api.common.upload_photo_to_storage", new_callable=AsyncMock) as mock_upload:
        # Return unique URL each time
        mock_upload.side_effect = (
            lambda *args, **kwargs: f"https://fake-gcp-url.com/fake_image_{uuid.uuid4().hex[:8]}.jpg"
        )
        yield mock_upload


@pytest.fixture(scope="function")
def mock_extract_firebase_uid():
    with patch("app.api.users.extract_firebase_user_uid") as mock_verify:
        mock_verify.return_value = "test_firebase_uid_123"
        yield mock_verify


def number_of_test_images_in_gcp() -> int:
    # Initialize client
    client = storage.Client()
    bucket_name = "swapwithus-listing-images"
    bucket = client.bucket(bucket_name)

    # List all blobs in test_images folder, excluding directory markers
    all_blobs = list(bucket.list_blobs(prefix="test_images/"))
    # Filter out directory markers (blobs ending with '/' that are empty)
    blobs = [blob for blob in all_blobs if not (blob.name.endswith("/") and blob.size == 0)]

    print(f"Total files in test_images/: {len(blobs)}")
    print("\nFiles:")
    for blob in blobs:
        print(f"  - {blob.name} ({blob.size} bytes)")

    return len(blobs), [blob.name for blob in blobs]
