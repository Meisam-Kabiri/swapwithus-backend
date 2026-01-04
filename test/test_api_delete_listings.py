from test.conftest import number_of_test_images_in_gcp
from test.factories import add_user, add_listing
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.main import app


async def detele_listing_template(create_db_pool, category: str):
    # Create test data instead of selecting from existing data
    owner_uid = await add_user(create_db_pool)
    listing_id = await add_listing(create_db_pool, owner_uid, category)
    print(f"Listing ID to delete: {listing_id}")
    number_of_homelistings_before = await create_db_pool.fetchval(
        f"SELECT COUNT(*) FROM {category}"
    )
    number_of_images_before_on_table = await create_db_pool.fetchval("SELECT COUNT(*) FROM images")
    number_of_test_images_on_gcp_before, _ = number_of_test_images_in_gcp()
    print(f"Testing deletion of home listing {listing_id}")
    with patch("app.api.listings.extract_firebase_user_uid", return_value=owner_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.delete(f"/api/listings/{category}/{listing_id}")
            print(res.json())
            assert res.status_code == 200
            number_of_homelistings_after = await create_db_pool.fetchval(
                f"SELECT COUNT(*) FROM {category}"
            )
            number_of_images_after_on_table = await create_db_pool.fetchval(
                "SELECT COUNT(*) FROM images"
            )
            number_of_test_images_on_gcp_after, _ = number_of_test_images_in_gcp()
            assert number_of_homelistings_after == number_of_homelistings_before - 1
            assert number_of_images_after_on_table < number_of_images_before_on_table
            assert number_of_test_images_on_gcp_after < number_of_test_images_on_gcp_before


async def test_delete_home_listing(create_db_pool):
    await detele_listing_template(create_db_pool, category="homes")


async def test_delete_book_listing(create_db_pool):
    await detele_listing_template(create_db_pool, category="books")


async def test_delete_clothing_listing(create_db_pool):
    await detele_listing_template(create_db_pool, category="clothes")


async def test_delete_caravan_listing(create_db_pool):
    await detele_listing_template(create_db_pool, category="caravans")
