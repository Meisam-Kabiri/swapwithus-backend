from test.factories import HomeListingUpdateCreateFactoryDict, fake_uploadfile_list

from httpx import ASGITransport, AsyncClient
import json 


from app.main import app
from unittest.mock import patch
from test.conftest import number_of_test_images_in_gcp
import pytest_asyncio
from app.services.gcp_image_service import upload_photo_to_storage as real_upload

async def test_update_listing_home(create_db_pool):
    

    number_of_homelistings_before = await create_db_pool.fetchval("SELECT COUNT(*) FROM homes")
    listing_id = await create_db_pool.fetchval("SELECT listing_id FROM homes LIMIT 1")
    number_of_images_before_on_table = await create_db_pool.fetchval("SELECT COUNT(*) FROM images")
    owner_uid = await create_db_pool.fetchval("SELECT owner_firebase_uid FROM homes WHERE listing_id = $1", listing_id)
    number_of_test_images_on_gcp_before = number_of_test_images_in_gcp()
    
    public_urls = await create_db_pool.fetch("SELECT public_url FROM images WHERE listing_id = $1 ORDER BY sort_order", listing_id)
    public_url_to_keep = public_urls[0] if public_urls else None
    public_url_to_delete = public_urls[1] if len(public_urls) > 1 else []
    
    
    
    
    update_lists_obj = HomeListingUpdateCreateFactoryDict()
    updated_fields = update_lists_obj.build_data_form()
    

    listing_data = HomeListingUpdateCreateFactoryDict()
    image_metadata = listing_data.build_image_metadata(3)
    image_metadata[1]["public_url"] = public_url_to_keep["public_url"] if public_url_to_keep else None  # Keep first image
    files = fake_uploadfile_list(3)


    updated_fields["images_metadata"] = image_metadata
    updated_fields["deleted_public_urls"] = [public_url_to_delete["public_url"]] if public_url_to_delete else []
    # Wrapper to force category="test_images" for all uploads during this test
    async def upload_with_test_category(photo, listing_id, category="test_images"):
        return await real_upload(photo, listing_id, "test_images")

    app.state.limiter.enabled = False

    with patch(
        "app.api.listings.upload_photo_to_storage",
        side_effect=upload_with_test_category,
    ) as mock_upload, patch(
        "app.api.listings.extract_firebase_user_uid", return_value=owner_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"api/listings/homes/{listing_id}",
                data={"listing": json.dumps(updated_fields)},
                files=[("images", (f.filename, f.file, "image/jpeg")) for f in files]

            )
            print(response.json())
            assert response.status_code == 200