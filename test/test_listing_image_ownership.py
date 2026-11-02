import json
from test.factories import add_listing, add_user
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.auth import extract_firebase_user_uid

BUCKET_URL = "https://storage.googleapis.com/swapwithus-listing-images/homes"


@pytest.fixture(autouse=True)
def rate_limiter_off():
    app.state.limiter.enabled = False
    yield
    app.dependency_overrides.clear()


async def add_home_with_photo(pool, photo_name):
    owner = await add_user(pool)
    listing_id = await add_listing(pool, owner, "homes", num_images=0)
    url = f"{BUCKET_URL}/{listing_id}_{photo_name}.jpg"
    await pool.execute(
        """
        INSERT INTO images (owner_firebase_uid, listing_id, category, public_url, cdn_url, is_hero, sort_order)
        VALUES ($1, $2, 'homes', $3, 'https://cdn.swapwithus.com/original.jpg', TRUE, 0)
        """,
        owner,
        listing_id,
        url,
    )
    return owner, listing_id, url


async def patch_listing(owner, listing_id, body):
    """Sends the update as owner and returns the response and the storage delete mock."""
    app.dependency_overrides[extract_firebase_user_uid] = lambda: owner
    storage_delete = AsyncMock(return_value=True)
    with patch("app.api.listings.delete_all_images_from_storage", new=storage_delete):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/listings/homes/{listing_id}", data={"listing": json.dumps(body)}
            )
    return response, storage_delete


async def image_urls(pool, listing_id):
    rows = await pool.fetch("SELECT public_url FROM images WHERE listing_id = $1", listing_id)
    return [row["public_url"] for row in rows]


async def test_cannot_delete_another_listings_photo(create_db_pool):
    _, victim_listing, victim_url = await add_home_with_photo(create_db_pool, "victim")
    attacker, attacker_listing, _ = await add_home_with_photo(create_db_pool, "attacker")

    response, storage_delete = await patch_listing(
        attacker, attacker_listing, {"imagesMetadata": [], "deletedPublicUrls": [victim_url]}
    )

    assert response.status_code == 200
    assert response.json()["images_deleted"] == 0
    storage_delete.assert_not_called()
    assert await image_urls(create_db_pool, victim_listing) == [victim_url]


async def test_mixed_delete_only_removes_own_photo_from_storage(create_db_pool):
    _, _, victim_url = await add_home_with_photo(create_db_pool, "victim")
    owner, listing_id, own_url = await add_home_with_photo(create_db_pool, "own")

    response, storage_delete = await patch_listing(
        owner, listing_id, {"imagesMetadata": [], "deletedPublicUrls": [own_url, victim_url]}
    )

    assert response.status_code == 200
    assert response.json()["images_deleted"] == 1
    storage_delete.assert_called_once_with([own_url])
    assert await image_urls(create_db_pool, listing_id) == []


async def test_cannot_attach_another_listings_photo(create_db_pool):
    _, _, victim_url = await add_home_with_photo(create_db_pool, "victim")
    attacker, attacker_listing, attacker_url = await add_home_with_photo(create_db_pool, "attacker")

    response, _ = await patch_listing(
        attacker,
        attacker_listing,
        {"imagesMetadata": [{"publicUrl": victim_url, "sortOrder": 0}]},
    )

    assert response.status_code == 400
    assert await image_urls(create_db_pool, attacker_listing) == [attacker_url]


async def test_owner_can_still_update_their_photo_but_not_its_cdn_url(create_db_pool):
    owner, listing_id, own_url = await add_home_with_photo(create_db_pool, "own")

    response, storage_delete = await patch_listing(
        owner,
        listing_id,
        {
            "imagesMetadata": [
                {
                    "publicUrl": own_url,
                    "cdnUrl": "https://evil.example/photo.jpg",
                    "caption": "New caption",
                    "sortOrder": 3,
                }
            ]
        },
    )

    assert response.status_code == 200
    storage_delete.assert_not_called()
    row = await create_db_pool.fetchrow(
        "SELECT caption, sort_order, cdn_url FROM images WHERE public_url = $1", own_url
    )
    assert row["caption"] == "New caption"
    assert row["sort_order"] == 3
    assert row["cdn_url"] == "https://cdn.swapwithus.com/original.jpg"
