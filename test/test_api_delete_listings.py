from httpx import ASGITransport, AsyncClient

from app.main import app

from unittest.mock import patch

from test.conftest import number_of_test_images_in_gcp


async def detele_listing_template(create_db_pool, category: str):
   # read a the first listing id from the home tables
    listing_id = await create_db_pool.fetchval(f"SELECT listing_id FROM {category} LIMIT 1")
    owner_uid = await create_db_pool.fetchval(
        f"SELECT owner_firebase_uid FROM {category} WHERE listing_id = $1", listing_id
    )
    number_of_homelistings_before = await create_db_pool.fetchval(f"SELECT COUNT(*) FROM {category}")
    number_of_images_before_on_table = await create_db_pool.fetchval("SELECT COUNT(*) FROM images")
    number_of_test_images_on_gcp_before, _ = number_of_test_images_in_gcp()
    print(f"Testing deletion of home listing {listing_id}")
    with patch("app.api.listings.extract_firebase_user_uid", return_value=owner_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.delete(f"/api/listings/{category}/{listing_id}")
            print(res.json())
            assert res.status_code == 200
            number_of_homelistings_after = await create_db_pool.fetchval(f"SELECT COUNT(*) FROM {category}")
            number_of_images_after_on_table = await create_db_pool.fetchval("SELECT COUNT(*) FROM images")
            number_of_test_images_on_gcp_after = number_of_test_images_in_gcp()
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
