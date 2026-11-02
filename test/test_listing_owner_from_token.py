import io
import json
from test.factories import add_listing, add_user
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.auth import extract_firebase_user_uid

UPLOADED_URL = "https://storage.googleapis.com/swapwithus-listing-images/homes/{}.jpg"


@pytest.fixture(autouse=True)
def rate_limiter_off():
    app.state.limiter.enabled = False
    yield
    app.dependency_overrides.clear()


async def create_home(logged_in_as, claimed_owner, email=None):
    app.dependency_overrides[extract_firebase_user_uid] = lambda: logged_in_as
    body = {
        "category": "homes",
        "ownerFirebaseUid": claimed_owner,
        "email": email or f"{uuid4().hex}@example.com",
        "name": "Fake Person",
        "accommodationType": "entire_place",
        "propertyType": "apartment",
        "maxGuests": 2,
        "country": "FI",
        "city": "Helsinki",
        "title": "A listing title",
        "imagesMetadata": [{"tag": "a", "caption": "b", "isHero": True, "sortOrder": 0}],
    }
    upload = AsyncMock(return_value=UPLOADED_URL.format(uuid4()))
    with patch("app.api.listings.upload_photo_to_storage", new=upload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/listings",
                data={"listing": json.dumps(body)},
                files=[("images", ("a.jpg", io.BytesIO(b"x"), "image/jpeg"))],
            )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def update_home(logged_in_as, listing_id, fields):
    app.dependency_overrides[extract_firebase_user_uid] = lambda: logged_in_as
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.patch(
            f"/api/listings/homes/{listing_id}",
            data={"listing": json.dumps({**fields, "imagesMetadata": []})},
        )


async def test_create_ignores_owner_claimed_in_the_body(create_db_pool):
    attacker = await add_user(create_db_pool)
    victim = await add_user(create_db_pool)

    listing_id = await create_home(attacker, claimed_owner=victim)

    listing_owner = await create_db_pool.fetchval(
        "SELECT owner_firebase_uid FROM homes WHERE listing_id = $1", listing_id
    )
    image_owner = await create_db_pool.fetchval(
        "SELECT owner_firebase_uid FROM images WHERE listing_id = $1", listing_id
    )
    assert listing_owner == attacker
    assert image_owner == attacker


async def test_create_cannot_invent_a_user_row(create_db_pool):
    attacker = await add_user(create_db_pool)
    invented_uid = f"never_registered_{uuid4()}"

    await create_home(attacker, claimed_owner=invented_uid)

    assert not await create_db_pool.fetchval(
        "SELECT 1 FROM users WHERE owner_firebase_uid = $1", invented_uid
    )


async def test_create_still_adds_a_first_time_users_row(create_db_pool):
    new_user = f"new_user_{uuid4()}"
    email = f"{uuid4().hex}@example.com"

    listing_id = await create_home(new_user, claimed_owner=new_user, email=email)

    assert await create_db_pool.fetchval(
        "SELECT email FROM users WHERE owner_firebase_uid = $1", new_user
    ) == email
    assert await create_db_pool.fetchval(
        "SELECT owner_firebase_uid FROM homes WHERE listing_id = $1", listing_id
    ) == new_user


async def test_update_cannot_change_owner_but_still_saves_other_fields(create_db_pool):
    owner = await add_user(create_db_pool)
    victim = await add_user(create_db_pool)
    listing_id = await add_listing(create_db_pool, owner, "homes", num_images=0)

    response = await update_home(
        owner, listing_id, {"ownerFirebaseUid": victim, "title": "Updated title"}
    )

    assert response.status_code == 200, response.text
    row = await create_db_pool.fetchrow(
        "SELECT owner_firebase_uid, title FROM homes WHERE listing_id = $1", listing_id
    )
    assert row["owner_firebase_uid"] == owner
    assert row["title"] == "Updated title"


async def test_update_cannot_change_listing_id(create_db_pool):
    owner = await add_user(create_db_pool)
    listing_id = await add_listing(create_db_pool, owner, "homes", num_images=0)

    response = await update_home(owner, listing_id, {"listingId": str(uuid4())})

    assert response.status_code == 200, response.text
    assert await create_db_pool.fetchval(
        "SELECT 1 FROM homes WHERE listing_id = $1", listing_id
    )
