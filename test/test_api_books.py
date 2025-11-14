from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import Request, UploadFile
from httpx import ASGITransport, AsyncClient

from app.main import app
from test.factories import UserCreateFactory, BookListingCreateFactory, fake_uploadfile_list
import pytest
import json




async def test_create_book_listing(create_db_pool):
    listing_data = BookListingCreateFactory.build()
    # listing_dict = listing_data.model_dump()
    # Convert only UUID to string if it exists
    # if listing_dict.get('listing_id') is not None:
    #     listing_dict['listing_id'] = str(listing_dict['listing_id'])


    user_data = UserCreateFactory.build()

    files = fake_uploadfile_list(2)
    
    # Merge both models
    combined = {
          **listing_data.model_dump(),
          **user_data.model_dump()
      }


    
    with patch("app.api.books.extract_firebase_user_uid") as mock_extract_uid:
        mock_extract_uid.return_value = user_data.owner_firebase_uid

        # Disable rate limiting for tests
        app.state.limiter.enabled = False

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

          
            
            response = await client.post("/api/books", data={"listing":  json.dumps(combined)},  files=[("images", (f.filename, f.file, "image/jpeg")) for f in files])
            
            assert response.status_code == 201
            data = response.json()
            assert data.get("message") == "Books listing created successfully"
            assert data.get("image_count") == 2
            assert "id" in data