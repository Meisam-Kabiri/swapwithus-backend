from app.services.gcp_image_service import upload_photo_to_storage, delete_image_from_storage
from uuid import uuid4
from io import BytesIO
from fastapi import UploadFile
import requests



fake_image = BytesIO(b"fake image data")
fake_image.name = f"test_image_{uuid4().hex[:8]}.jpg" 


fake_upload_file = UploadFile(file = fake_image, filename=fake_image.name, headers={"content-type": "image/jpeg"})
# fake_upload_file.content_type = "image/jpeg"

async def test_upload_to_gcp():
    url = await upload_photo_to_storage(fake_upload_file,  listing_id = str(uuid4())[:4], category = "test_images") 
    assert url.startswith("https://storage.googleapis.com/")
    response = requests.head(url, allow_redirects=True)
    assert response.status_code in (401, 403)
    return url
    
    
async def test_delete_from_gcp():
  url = await upload_photo_to_storage(fake_upload_file,  listing_id = str(uuid4())[:4], category = "test_images")
  deleted = await delete_image_from_storage(url)
  assert deleted is True
  
