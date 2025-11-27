from test.factories import fake_uploadfile_list

from app.api.homes import upload_photo_to_storage
from app.services.gcp_image_service import delete_all_images_from_storage

from test.conftest import number_of_test_images_in_gcp


async def test_real_upload_delete_images_to_gcp():
    """
      Test real upload and deletion of images to/from GCP Storage.
      We use the same bucket as in production so be cautious, but different folder(category): "test_images".
    """
    num_files_on_gcp_before = number_of_test_images_in_gcp()
    files = fake_uploadfile_list(1)
    uploaded_urls = []
    for file in files:
        url = await upload_photo_to_storage(file, listing_id="test_listing_123", category="test_images")
        uploaded_urls.append(url)
        print(f"Uploaded URL: {url}")
    assert len(uploaded_urls) == 1
    assert all(url.startswith("https://storage.googleapis.com/") for url in uploaded_urls)
    assert num_files_on_gcp_before + 1 == number_of_test_images_in_gcp()

    await delete_all_images_from_storage(uploaded_urls)
    assert num_files_on_gcp_before == number_of_test_images_in_gcp()
