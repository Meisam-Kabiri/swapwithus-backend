import os
from io import BytesIO
from test.conftest import number_of_test_images_in_gcp
from test.factories import fake_uploadfile_list
from uuid import uuid4

import requests
from fastapi import UploadFile

from app.services.gcp_image_service import (delete_all_images_from_storage,
                                            upload_photo_to_storage)

fake_image = BytesIO(b"fake image data")
fake_image.name = f"test_image_{uuid4().hex[:8]}.jpg"


fake_upload_file = UploadFile(
    file=fake_image, filename=fake_image.name, headers={"content-type": "image/jpeg"}
)


async def test_real_upload_delete_images_to_gcp():
    """
    Test real upload and deletion of images to/from GCP Storage.
    We use the same bucket as in production so be cautious, but different folder(category): "test_images".
    """
    num_files_on_gcp_before, _ = number_of_test_images_in_gcp()
    files = fake_uploadfile_list(1)
    uploaded_urls = []
    for file in files:
        url = await upload_photo_to_storage(
            file, listing_id="test_listing_123", category="test_images"
        )
        uploaded_urls.append(url)
        print(f"Uploaded URL: {url}")
    assert len(uploaded_urls) == 1
    assert all(url.startswith("https://storage.googleapis.com/") for url in uploaded_urls)
    assert num_files_on_gcp_before + 1 == number_of_test_images_in_gcp()[0]
    response = requests.head(url, allow_redirects=True)
    assert response.status_code in (401, 403)  # GCP buckets are private by default

    deleted = await delete_all_images_from_storage(uploaded_urls)
    assert deleted is True
    assert num_files_on_gcp_before == number_of_test_images_in_gcp()[0]
