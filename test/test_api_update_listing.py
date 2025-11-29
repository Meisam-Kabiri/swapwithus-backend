from test.factories import HomeListingUpdateCreateFactoryDict, fake_uploadfile_list

from httpx import ASGITransport, AsyncClient
import json 


from app.main import app
from unittest.mock import patch
from test.conftest import number_of_test_images_in_gcp
import pytest_asyncio
from app.services.gcp_image_service import upload_photo_to_storage as real_upload

async def test_update_listing_home(create_db_pool):
    

    num_of_new_images = 3
    number_of_homelistings_before = await create_db_pool.fetchval("SELECT COUNT(*) FROM homes")
    listing_id = await create_db_pool.fetchval("SELECT listing_id FROM homes LIMIT 1")
    number_of_images_before_on_table = await create_db_pool.fetchval("SELECT COUNT(*) FROM images")
    public_urls_on_database_before = await create_db_pool.fetch("SELECT public_url FROM images WHERE listing_id = $1 ORDER BY sort_order", listing_id)
    owner_uid = await create_db_pool.fetchval("SELECT owner_firebase_uid FROM homes WHERE listing_id = $1", listing_id)
    number_of_test_images_on_gcp_before, images_list_on_gcp_before = number_of_test_images_in_gcp()
    
    
    # we keep one image, delete one image and add two new image (there are three iamges in totatl in the update that are sent)
    public_urls = [dict(urls).get("public_url") for urls in public_urls_on_database_before]
    public_url_to_keep = public_urls[0] if public_urls else None
    public_url_to_delete = public_urls[1] if len(public_urls) > 1 else []
    
    
    
    # The first image must be on the database after update
    # No other iamges must be on the database after update
    
    update_lists_obj = HomeListingUpdateCreateFactoryDict()
    updated_fields = update_lists_obj.build_data_form()
    

    listing_data = HomeListingUpdateCreateFactoryDict()
    image_metadata = listing_data.build_image_metadata(num_of_new_images)
    image_metadata[1]["public_url"] = public_url_to_keep if public_url_to_keep else None  # Keep first image
    files = fake_uploadfile_list(num_of_new_images)


    updated_fields["images_metadata"] = image_metadata
    updated_fields["deleted_public_urls"] = [public_url_to_delete] if public_url_to_delete else []
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
            public_urls_on_database_after = await create_db_pool.fetch("SELECT public_url FROM images WHERE listing_id = $1 ORDER BY sort_order", listing_id)
            number_of_images_after_on_table = await create_db_pool.fetchval("SELECT COUNT(*) FROM images WHERE listing_id = $1", listing_id)
            number_of_test_images_on_gcp_after, images_list_on_gcp_after = number_of_test_images_in_gcp()
            assert response.status_code == 200
            assert number_of_homelistings_before == await create_db_pool.fetchval("SELECT COUNT(*) FROM homes")
            assert number_of_images_after_on_table == len(public_urls_on_database_before) + num_of_new_images-2  # -2 means out of #num_new_image one image was alraedy there and one images was deleted
            assert public_url_to_keep in [dict(url).get("public_url") for url in public_urls_on_database_after]
            assert public_url_to_delete not in [url["public_url"] for url in public_urls_on_database_after]
            assert number_of_test_images_on_gcp_after == number_of_test_images_on_gcp_before+num_of_new_images-2
            assert any(file_name in public_url_to_keep for file_name in images_list_on_gcp_after)
            assert all(file_name not in public_url_to_delete for file_name in images_list_on_gcp_after)
            
             
            
            