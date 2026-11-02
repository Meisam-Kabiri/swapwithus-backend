import io
import json
from test.factories import add_user
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.auth import FirebaseUser, get_firebase_user


@pytest.fixture(autouse=True)
def rate_limiter_off():
    app.state.limiter.enabled = False
    yield
    app.dependency_overrides.clear()


def login(uid, email, email_verified=True):
    app.dependency_overrides[get_firebase_user] = lambda: FirebaseUser(uid, email, email_verified)


def unique_email():
    return f"{uuid4().hex}@example.com"


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def post_user(uid, body_email, is_email_verified=True):
    async with client() as c:
        return await c.post(
            "/api/users",
            json={
                "ownerFirebaseUid": uid,
                "email": body_email,
                "name": "Ada Lovelace",
                "isEmailVerified": is_email_verified,
            },
        )


async def post_listing(uid, body_email):
    """Returns the response and the upload mock."""
    body = {
        "category": "homes",
        "ownerFirebaseUid": uid,
        "email": body_email,
        "name": "Ada Lovelace",
        "accommodationType": "entire_place",
        "propertyType": "apartment",
        "maxGuests": 2,
        "country": "FI",
        "city": "Helsinki",
        "title": "A listing title",
        "imagesMetadata": [{"tag": "a", "caption": "b", "isHero": True, "sortOrder": 0}],
    }
    url = f"https://storage.googleapis.com/swapwithus-listing-images/homes/{uuid4()}.jpg"
    upload = AsyncMock(return_value=url)
    with patch("app.api.listings.upload_photo_to_storage", new=upload):
        async with client() as c:
            response = await c.post(
                "/api/listings",
                data={"listing": json.dumps(body)},
                files=[("images", ("a.jpg", io.BytesIO(b"x"), "image/jpeg"))],
            )
    return response, upload


async def saved_user(pool, uid):
    return await pool.fetchrow(
        "SELECT email, is_email_verified FROM users WHERE owner_firebase_uid = $1", uid
    )


async def test_signup_saves_token_email_not_the_claimed_one(create_db_pool):
    uid, real_email = f"user_{uuid4()}", unique_email()
    login(uid, real_email)

    response = await post_user(uid, body_email=unique_email())

    assert response.status_code == 201, response.text
    assert (await saved_user(create_db_pool, uid))["email"] == real_email


async def test_signup_cannot_claim_it_is_verified(create_db_pool):
    uid = f"user_{uuid4()}"
    login(uid, unique_email(), email_verified=False)

    response = await post_user(uid, body_email=unique_email(), is_email_verified=True)

    assert response.status_code == 201, response.text
    assert (await saved_user(create_db_pool, uid))["is_email_verified"] is False


async def test_signup_without_an_email_gets_a_clear_error(create_db_pool):
    uid = f"user_{uuid4()}"
    login(uid, None)

    response = await post_user(uid, body_email=None)

    assert response.status_code == 400
    assert "email" in response.json()["detail"]
    assert await saved_user(create_db_pool, uid) is None


async def test_first_listing_saves_token_email_not_the_claimed_one(create_db_pool):
    uid, real_email = f"user_{uuid4()}", unique_email()
    login(uid, real_email)

    response, _ = await post_listing(uid, body_email=unique_email())

    assert response.status_code == 200, response.text
    assert (await saved_user(create_db_pool, uid))["email"] == real_email


async def test_new_user_without_an_email_is_rejected_before_any_upload(create_db_pool):
    uid = f"user_{uuid4()}"
    login(uid, None)

    response, upload = await post_listing(uid, body_email="")

    assert response.status_code == 400
    upload.assert_not_called()
    assert await saved_user(create_db_pool, uid) is None


async def test_existing_user_without_a_token_email_can_still_create_a_listing(create_db_pool):
    uid = await add_user(create_db_pool)
    original_email = (await saved_user(create_db_pool, uid))["email"]
    login(uid, None)

    response, _ = await post_listing(uid, body_email="")

    assert response.status_code == 200, response.text
    assert (await saved_user(create_db_pool, uid))["email"] == original_email
