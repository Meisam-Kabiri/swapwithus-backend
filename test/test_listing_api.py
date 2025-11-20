from httpx import AsyncClient, ASGITransport
import pytest
from unittest.mock import patch 
from uuid import uuid4
import pytest_asyncio

from app.main import app

@pytest_asyncio.fixture(scope="function")
async def get_listing_id_and_owner_id(create_db_pool):
    async with create_db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT listing_id, owner_firebase_uid FROM books LIMIT 1")
        yield row["listing_id"], row["owner_firebase_uid"]
# async def test_get_all_my_listings_n(create_db_pool):
#   with patch("app.api.listings.extract_firebase_user_uid") as mock_extract_uid:
#     # get the first user_id from the book database
#     async with create_db_pool.acquire() as conn:
#         user_id = await conn.fetchval("SELECT owner_firebase_uid FROM books LIMIT 1")
#         print(f"Using user_id: {user_id} for test")
    
#     mock_extract_uid.return_value = user_id
#     async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
#         response = await client.get("api/listings/me")
#         print(response.json())
#         res = response.json()
#         assert response.status_code == 200
#          # Check book structure
#         book = res["books"][0]
#         assert "listing_id" in book
#         assert "owner_firebase_uid" in book
#         assert book["owner_firebase_uid"] == user_id  # Verify it's the right user
#         assert "title" in book
#         assert "images" in book
#         assert isinstance(book["images"], list)

        
async def test_delete_my_listing_not_authorized(create_db_pool, get_listing_id_and_owner_id):
      listing_id, owner_uid = get_listing_id_and_owner_id
      
   
      print(f"Testing deletion of listing {listing_id} owned by {owner_uid}")
      with patch("app.api.listings.extract_firebase_user_uid") as mock_extract_uid:
        # get a user_id from the book database
        mock_extract_uid.return_value = str(uuid4())  # Random UID that doesn't own the listing
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.delete(f"api/listings/book/{listing_id}")
            print(res.json())
            assert res.status_code == 403

async def test_delete_my_listing_authorized(create_db_pool, get_listing_id_and_owner_id):
      listing_id, owner_uid = get_listing_id_and_owner_id
      
   
      print(f"Testing deletion of listing {listing_id} owned by {owner_uid}")
      with patch("app.api.listings.extract_firebase_user_uid") as mock_extract_uid:
        # get a user_id from the book database
        mock_extract_uid.return_value = owner_uid  # Random UID that doesn't own the listing
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.delete(f"api/listings/book/{listing_id}")
            print(res.json())
            assert res.status_code == 200