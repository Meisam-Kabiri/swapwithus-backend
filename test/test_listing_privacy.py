import io
import json
from test.factories import (CaravanListingCreateFactory, ClothingListingCreateFactory, add_listing,
                            add_user)
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.auth import get_optional_firebase_uid

ADDRESS_KEYS = {"streetAddress", "postalCode", "latitude", "longitude"}
OWNER_KEYS = {"email", "name", "profileImage"}
OWNER_DETAILS = {
    "email": "ada@example.com",
    "name": "Ada Lovelace",
    "profile_image": "https://cdn.test/ada.jpg",
}


@pytest.fixture(autouse=True)
def no_conversations():
    """No accepted Firestore conversations unless a test sets some."""
    app.state.limiter.enabled = False
    with patch("app.services.listing_privacy._accepted_conversations", return_value=[]) as mock:
        yield mock
    app.dependency_overrides.clear()


def view_as(uid):
    app.dependency_overrides[get_optional_firebase_uid] = lambda: uid


async def get(path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


async def make_home(pool):
    owner = await add_user(pool, name="Ada Lovelace")
    await pool.execute(
        "UPDATE users SET profile_image = 'https://cdn.test/ada.jpg' WHERE owner_firebase_uid = $1",
        owner,
    )
    listing_id = await add_listing(
        pool,
        owner,
        "homes",
        num_images=0,
        street_address="1 Secret Street",
        postal_code="00100",
        latitude=60.17,
        longitude=24.94,
    )
    return owner, listing_id


async def add_chain(pool, status, legs):
    """legs: (from_user, to_user, listing_id, accepted)"""
    chain_id = await pool.fetchval(
        "INSERT INTO swap_chains (status) VALUES ($1) RETURNING chain_id", status
    )
    for from_user, to_user, listing_id, accepted in legs:
        await pool.execute(
            """
            INSERT INTO swap_legs (chain_id, from_user, to_user, listing_id, category, accepted)
            VALUES ($1, $2, $3, $4::uuid, 'homes', $5)
            """,
            chain_id, from_user, to_user, listing_id, accepted,
        )
    return chain_id


async def test_anonymous_never_gets_exact_location(create_db_pool):
    _, listing_id = await make_home(create_db_pool)
    view_as(None)

    detail = await get(f"api/listings/homes/{listing_id}")
    assert not ADDRESS_KEYS & detail.keys()
    assert detail["city"]


@pytest.mark.parametrize("category", ["homes", "all"])
async def test_browse_never_returns_exact_location(create_db_pool, category):
    owner, listing_id = await make_home(create_db_pool)
    # Browse only returns listings that have at least one image
    await create_db_pool.execute(
        """
        INSERT INTO images (owner_firebase_uid, listing_id, category, public_url, cdn_url, is_hero, sort_order)
        VALUES ($1, $2, 'homes', $3, $3, TRUE, 0)
        """,
        owner,
        listing_id,
        f"https://storage.test/{listing_id}.jpg",
    )
    data = await get(f"api/browse?category={category}&page=1&page_size=100")
    assert data["listings"]
    for listing in data["listings"]:
        assert not ADDRESS_KEYS & listing.keys()


async def test_owner_gets_exact_location(create_db_pool):
    owner, listing_id = await make_home(create_db_pool)
    view_as(owner)

    detail = await get(f"api/listings/homes/{listing_id}")
    assert detail["streetAddress"] == "1 Secret Street"
    assert detail["postalCode"] == "00100"
    assert detail["latitude"] == 60.17


@pytest.mark.parametrize(
    "status,revealed",
    [("pending", False), ("cancelled", False), ("accepted", True), ("completed", True)],
)
async def test_swap_partner_gets_location_only_once_accepted(create_db_pool, status, revealed):
    owner, listing_id = await make_home(create_db_pool)
    guest = await add_user(create_db_pool)
    guest_listing = await add_listing(create_db_pool, guest, "homes", num_images=0)
    await add_chain(
        create_db_pool,
        status,
        [(owner, guest, listing_id, True), (guest, owner, guest_listing, True)],
    )
    view_as(guest)

    detail = await get(f"api/listings/homes/{listing_id}")
    assert ("streetAddress" in detail) is revealed


async def test_chain_not_giving_the_real_owners_home_reveals_nothing(create_db_pool):
    _, victim_listing = await make_home(create_db_pool)
    attacker = await add_user(create_db_pool)
    accomplice = await add_user(create_db_pool)
    await add_chain(create_db_pool, "accepted", [(accomplice, attacker, victim_listing, True)])
    view_as(attacker)

    detail = await get(f"api/listings/homes/{victim_listing}")
    assert "streetAddress" not in detail


async def test_accepted_conversation_reveals_location(create_db_pool, no_conversations):
    owner, listing_id = await make_home(create_db_pool)
    guest = await add_user(create_db_pool)
    no_conversations.return_value = [
        {
            "requester_uid": guest,
            "recipient_uid": owner,
            "recipient_listing_id": listing_id,
            "participants": [guest, owner],
        }
    ]
    view_as(guest)

    detail = await get(f"api/listings/homes/{listing_id}")
    assert detail["streetAddress"] == "1 Secret Street"


async def test_conversation_naming_someone_elses_listing_reveals_nothing(
    create_db_pool, no_conversations
):
    _, victim_listing = await make_home(create_db_pool)
    attacker = await add_user(create_db_pool)
    accomplice = await add_user(create_db_pool)
    no_conversations.return_value = [
        {
            "requester_uid": attacker,
            "recipient_uid": accomplice,
            "recipient_listing_id": victim_listing,
            "participants": [attacker, accomplice],
        }
    ]
    view_as(attacker)

    detail = await get(f"api/listings/homes/{victim_listing}")
    assert "streetAddress" not in detail


async def test_firestore_failure_keeps_location_private(create_db_pool, no_conversations):
    _, listing_id = await make_home(create_db_pool)
    viewer = await add_user(create_db_pool)
    no_conversations.side_effect = RuntimeError("firestore down")
    view_as(viewer)

    detail = await get(f"api/listings/homes/{listing_id}")
    assert "streetAddress" not in detail


async def test_favorites_hide_exact_location(create_db_pool):
    from app.middleware.auth import extract_firebase_user_uid

    _, listing_id = await make_home(create_db_pool)
    fan = await add_user(create_db_pool)
    await create_db_pool.execute(
        "INSERT INTO favorites (owner_firebase_uid, listing_id) VALUES ($1, $2)",
        fan,
        listing_id,
    )
    app.dependency_overrides[extract_firebase_user_uid] = lambda: fan

    favorites = await get("api/favorites")
    assert len(favorites) == 1
    assert not {"street_address", "postal_code", "latitude", "longitude"} & favorites[0].keys()


async def test_public_profile_hides_surname_and_photo(create_db_pool):
    owner, _ = await make_home(create_db_pool)
    stranger = await add_user(create_db_pool)

    for viewer in (None, stranger):
        view_as(viewer)
        profile = await get(f"api/users/{owner}")
        assert profile["name"] == "Ada"
        assert profile["profileImage"] is None


async def test_own_profile_is_complete(create_db_pool):
    owner, _ = await make_home(create_db_pool)
    view_as(owner)

    profile = await get(f"api/users/{owner}")
    assert profile["name"] == "Ada Lovelace"
    assert profile["profileImage"] == "https://cdn.test/ada.jpg"


async def test_accepted_partner_sees_full_identity(create_db_pool):
    owner, listing_id = await make_home(create_db_pool)
    guest = await add_user(create_db_pool)
    guest_listing = await add_listing(create_db_pool, guest, "homes", num_images=0)
    await add_chain(
        create_db_pool,
        "accepted",
        [(owner, guest, listing_id, True), (guest, owner, guest_listing, True)],
    )
    view_as(guest)

    profile = await get(f"api/users/{owner}")
    assert profile["name"] == "Ada Lovelace"
    assert profile["profileImage"] == "https://cdn.test/ada.jpg"


async def test_being_named_in_a_chain_does_not_unlock_a_stranger(create_db_pool):
    victim = await add_user(create_db_pool, name="Ada Lovelace")
    attacker = await add_user(create_db_pool)
    attacker_listing = await add_listing(create_db_pool, attacker, "homes", num_images=0)
    await add_chain(create_db_pool, "accepted", [(attacker, victim, attacker_listing, True)])
    view_as(attacker)

    profile = await get(f"api/users/{victim}")
    assert profile["name"] == "Ada"


async def add_listing_with_owner_details(pool, category):
    owner = await add_user(pool)
    listing_id = await add_listing(pool, owner, category, num_images=0)
    # Rows created before the models dropped these fields still have them filled in
    await pool.execute(
        f"UPDATE {category} SET email = $1, name = $2, profile_image = $3 WHERE listing_id = $4",
        OWNER_DETAILS["email"],
        OWNER_DETAILS["name"],
        OWNER_DETAILS["profile_image"],
        listing_id,
    )
    await pool.execute(
        """
        INSERT INTO images (owner_firebase_uid, listing_id, category, public_url, cdn_url, is_hero, sort_order)
        VALUES ($1, $2, $3, $4, $4, TRUE, 0)
        """,
        owner,
        listing_id,
        category,
        f"https://storage.test/{listing_id}.jpg",
    )
    return owner, listing_id


@pytest.mark.parametrize("category", ["clothes", "caravans"])
async def test_listing_detail_never_returns_owner_details(create_db_pool, category):
    owner, listing_id = await add_listing_with_owner_details(create_db_pool, category)

    # Nobody gets them here, including the owner: /users/{uid} decides who sees them
    for viewer in (None, await add_user(create_db_pool), owner):
        view_as(viewer)
        detail = await get(f"api/listings/{category}/{listing_id}")
        assert not OWNER_KEYS & detail.keys()
        assert detail["ownerFirebaseUid"] == owner


@pytest.mark.parametrize("category", ["clothes", "caravans", "all"])
async def test_browse_never_returns_owner_details(create_db_pool, category):
    for listing_category in ("clothes", "caravans"):
        await add_listing_with_owner_details(create_db_pool, listing_category)

    data = await get(f"api/browse?category={category}&page=1&page_size=100")
    assert data["listings"]
    for listing in data["listings"]:
        assert not OWNER_KEYS & listing.keys()
    assert "ada@example.com" not in str(data)


async def test_accepted_partner_gets_location_but_not_owner_details_from_listing(create_db_pool):
    owner, listing_id = await make_home(create_db_pool)
    await create_db_pool.execute(
        "UPDATE homes SET email = $1, name = $2, profile_image = $3 WHERE listing_id = $4",
        OWNER_DETAILS["email"],
        OWNER_DETAILS["name"],
        OWNER_DETAILS["profile_image"],
        listing_id,
    )
    guest = await add_user(create_db_pool)
    await add_chain(create_db_pool, "accepted", [(owner, guest, listing_id, True)])
    view_as(guest)

    detail = await get(f"api/listings/homes/{listing_id}")
    assert detail["streetAddress"] == "1 Secret Street"
    assert not OWNER_KEYS & detail.keys()


async def test_favorites_hide_owner_details_on_old_home_rows(create_db_pool):
    from app.middleware.auth import extract_firebase_user_uid

    _, listing_id = await make_home(create_db_pool)
    await create_db_pool.execute(
        "UPDATE homes SET email = $1, name = $2, profile_image = $3 WHERE listing_id = $4",
        OWNER_DETAILS["email"],
        OWNER_DETAILS["name"],
        OWNER_DETAILS["profile_image"],
        listing_id,
    )
    fan = await add_user(create_db_pool)
    await create_db_pool.execute(
        "INSERT INTO favorites (owner_firebase_uid, listing_id) VALUES ($1, $2)", fan, listing_id
    )
    app.dependency_overrides[extract_firebase_user_uid] = lambda: fan

    favorites = await get("api/favorites")
    assert len(favorites) == 1
    assert not {"email", "name", "profile_image"} & favorites[0].keys()


@pytest.mark.parametrize(
    "category,factory",
    [("clothes", ClothingListingCreateFactory), ("caravans", CaravanListingCreateFactory)],
)
async def test_new_listing_saves_owner_details_on_users_only(create_db_pool, category, factory):
    from app.middleware.auth import extract_firebase_user_uid

    owner = f"new_owner_{uuid4()}"
    email = f"{uuid4().hex}@example.com"
    app.dependency_overrides[extract_firebase_user_uid] = lambda: owner
    listing = factory.build().model_dump(mode="json", exclude={"listing_id"})
    listing.update(
        category=category,
        owner_firebase_uid=owner,
        email=email,
        name="Ada Lovelace",
        profileImage="https://cdn.test/ada.jpg",
        imagesMetadata=[{"tag": "front", "caption": "x", "isHero": True, "sortOrder": 0}],
    )

    with patch(
        "app.api.listings.upload_photo_to_storage",
        new=AsyncMock(
            return_value=f"https://storage.googleapis.com/swapwithus-listing-images/{category}/a.jpg"
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/listings",
                data={"listing": json.dumps(listing)},
                files=[("images", ("a.jpg", io.BytesIO(b"x"), "image/jpeg"))],
            )
    assert response.status_code == 200, response.text

    row = await create_db_pool.fetchrow(
        f"SELECT email, name, profile_image FROM {category} WHERE owner_firebase_uid = $1", owner
    )
    assert tuple(row) == (None, None, None)
    user = await create_db_pool.fetchrow(
        "SELECT email, name FROM users WHERE owner_firebase_uid = $1", owner
    )
    assert tuple(user) == (email, "Ada Lovelace")
