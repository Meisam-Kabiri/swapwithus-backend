from test.factories import HomeListingCreateFactory, UserCreateFactory, fake_uploadfile_list, ClothingListingCreateFactory, BookListingCreateFactory, CaravanListingCreateFactory

from httpx import ASGITransport, AsyncClient

from app.main import app

from unittest.mock import patch

from test.conftest import number_of_test_images_in_gcp


async def create_listing_template(create_db_pool, category: str):
    from app.services.gcp_image_service import upload_photo_to_storage as real_upload
    from app.models.image import ImageMetadataItem
    import json

    number_of_homelistings_before = await create_db_pool.fetchval(f"SELECT COUNT(*) FROM {category}")
    number_of_images_before_on_table = await create_db_pool.fetchval("SELECT COUNT(*) FROM images")
    number_of_test_images_on_gcp_before, _ = number_of_test_images_in_gcp()

    if category == "homes":
      listing_data = HomeListingCreateFactory.build()
    elif category == "books":
      listing_data = BookListingCreateFactory.build()
    elif category == "clothes":
      listing_data = ClothingListingCreateFactory.build()
    elif category == "caravans":
      listing_data = CaravanListingCreateFactory.build()
    else:
      raise ValueError("Invalid category for listing creation test.")

    user_data = UserCreateFactory.build()
    files = fake_uploadfile_list(2)

    # Debug: Check which fields are too long
    print("\n=== Checking field lengths ===")
    for key, value in listing_data.model_dump().items():
        if isinstance(value, str) and len(value) > 50:
            print(f"WARNING: {key} = {len(value)} chars: '{value[:80]}...'")

    # Create image metadata for each file
    images_metadata = [
        ImageMetadataItem(caption=f"Test image {i}", tag="test", is_hero=(i == 0), sort_order=i)
        for i in range(len(files))
    ]

    # Combine all data into one JSON (as the API expects)
    # Use mode='json' to convert UUIDs and other non-serializable types to strings
    combined_data = {
        **listing_data.model_dump(mode='json'),
        **user_data.model_dump(mode='json'),
        "images_metadata": [img.model_dump(mode='json') for img in images_metadata],
        "category": category
    }

    app.state.limiter.enabled = False

    # Wrapper to force category="test_images" for all uploads during this test
    async def upload_with_test_category(photo, listing_id, category="test_images"):
        return await real_upload(photo, listing_id, "test_images")

    # Mock authentication to return a test user ID
    with patch("app.api.listings.extract_firebase_user_uid", return_value="test_firebase_uid_123"):
        with patch("app.api.listings.upload_photo_to_storage", side_effect=upload_with_test_category):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                result = await client.post(
                    "/api/listings",
                    data={"listing": json.dumps(combined_data)},
                    files=[("images", (f.filename, f.file, "image/jpeg")) for f in files],
                )
                print(f"Status: {result.status_code}")
                print(f"Response: {result.text}")
                assert result.status_code in (200, 201)
                number_of_homelistings_after = await create_db_pool.fetchval(f"SELECT COUNT(*) FROM {category}")
                number_of_images_after_on_table = await create_db_pool.fetchval("SELECT COUNT(*) FROM images")
                number_of_test_images_on_gcp_after, _ = number_of_test_images_in_gcp()
                assert number_of_homelistings_after == number_of_homelistings_before + 1
                assert number_of_images_after_on_table == number_of_images_before_on_table + len(files)
                assert number_of_test_images_on_gcp_after == number_of_test_images_on_gcp_before + len(files)



async def test_create_home_listing(create_db_pool):
    await create_listing_template(create_db_pool, category="homes")

async def test_create_book_listing(create_db_pool):
    await create_listing_template(create_db_pool, category="books")

async def test_create_clothing_listing(create_db_pool):
    await create_listing_template(create_db_pool, category="clothes")

async def test_create_caravan_listing(create_db_pool):
    await create_listing_template(create_db_pool, category="caravans")
