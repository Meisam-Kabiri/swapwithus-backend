from test.factories import HomeListingCreateFactory, UserCreateFactory, fake_uploadfile_list
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import Request, UploadFile
from httpx import ASGITransport, AsyncClient

from app.main import app

async def test_create_home_listing(create_db_pool, mock_extract_firebase_uid):
    listing_data = HomeListingCreateFactory.build()
    user_data = UserCreateFactory.build()
    files = fake_uploadfile_list(2)
    
    app.state.limiter.enabled = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
       resutl = client.post("/api/homes", data={"listing": listing_data.model_dump_json()},  files=[("images", (f.filename, f.file, "image/jpeg")) for f in fake_uploadfile_list(2)])
       print(resutl)