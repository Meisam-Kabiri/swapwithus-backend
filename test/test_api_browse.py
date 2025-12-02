import logging

from httpx import ASGITransport, AsyncClient

from app.main import app

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def test_browse_homes_pagination(create_db_pool):
    number_of_homelistings = await create_db_pool.fetchval("SELECT COUNT(*) FROM homes")
    number_of_images = await create_db_pool.fetchval(
        "SELECT COUNT(*) FROM images where category='homes'"
    )
    logger.info(f"Total number of home listings in DB: {number_of_homelistings}")
    logger.info(f"Total number of images in DB: {number_of_images}")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("api/browse?category=homes&page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert "category" in data
        assert data["category"] == "homes"
        assert "listings" in data
        assert isinstance(data["listings"], list)
        assert len(data["listings"]) <= 5  # page_size is 5
        assert "pagination" in data
        pagination = data["pagination"]
        assert pagination["page"] == 1
        assert pagination["page_size"] == 5
        assert "total_items" in pagination
        assert "total_pages" in pagination
        assert "has_next" in pagination
        assert "has_previous" in pagination
        assert pagination["total_items"] == number_of_homelistings


async def test_one_home_listing(create_db_pool):
    # Fetch one listing from the database to test
    listing = await create_db_pool.fetchrow("SELECT * FROM homes LIMIT 1")
    listing_id = listing["listing_id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"api/listings/homes/{listing_id}")
        assert response.status_code == 200
        data = response.json()
        assert "listingId" in data
        assert data["listingId"] == str(listing_id)
        assert "ownerFirebaseUid" in data
        assert "title" in data
        assert "images" in data
        assert isinstance(data["images"], list)
