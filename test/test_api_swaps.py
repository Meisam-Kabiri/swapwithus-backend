from unittest.mock import patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app
from test.factories import SwapCreateFactory, UserCreateFactory, add_user, add_listing


# ============================================
# TESTS
# ============================================


async def test_create_swap_success(create_db_pool):
    """Test successfully creating a swap between two users"""
    app.state.limiter.enabled = False

    # Create two test users
    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    # Create two listings in the same category
    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    # Create swap request
    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
        "conversationId": "test_conversation_123",
    }

    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/swaps", json=swap_data)

            assert response.status_code == 201
            data = response.json()
            assert data["userAUid"] == user_a_uid
            assert data["userBUid"] == user_b_uid
            assert data["status"] == "pending"
            assert data["listingAId"] == listing_a_id
            assert data["listingBId"] == listing_b_id
            assert data["category"] == "books"
            assert "swapId" in data

            # Verify in database
            swap = await create_db_pool.fetchrow(
                "SELECT * FROM swaps WHERE swap_id = $1", data["swapId"]
            )
            assert swap is not None
            assert swap["status"] == "pending"


async def test_create_swap_with_self_fails(create_db_pool):
    """Test that creating a swap with yourself fails"""
    app.state.limiter.enabled = False

    user_uid = await add_user(create_db_pool, uid=uuid4().hex[:20])

    listing_a_id = await add_listing(create_db_pool, user_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_uid, "books")

    swap_data = {
        "userBUid": user_uid,  # Same as user_a
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/swaps", json=swap_data)

            assert response.status_code == 400
            assert "Cannot create swap with yourself" in response.json()["detail"]


async def test_create_swap_different_categories_fails(create_db_pool):
    """Test that swapping items from different categories fails"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "clothes")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "clothes",
    }

    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/swaps", json=swap_data)

            assert response.status_code == 400
            assert "different categories" in response.json()["detail"]


async def test_create_duplicate_swap_fails(create_db_pool):
    """Test that creating a duplicate swap fails"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # First swap should succeed
            response1 = await client.post("/api/swaps", json=swap_data)
            assert response1.status_code == 201

            # Second swap should fail
            response2 = await client.post("/api/swaps", json=swap_data)
            assert response2.status_code == 400
            assert "already exists" in response2.json()["detail"]


async def test_get_my_swaps(create_db_pool):
    """Test getting all swaps for a user"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    # Create a swap
    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create swap
            await client.post("/api/swaps", json=swap_data)

            # Get swaps for user A
            response = await client.get("/api/swaps")
            assert response.status_code == 200
            data = response.json()
            assert "swaps" in data
            assert len(data["swaps"]) >= 1
            assert data["swaps"][0]["userAUid"] == user_a_uid

    # Verify user B also sees the swap
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_b_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/swaps")
            assert response.status_code == 200
            data = response.json()
            assert len(data["swaps"]) >= 1


async def test_get_my_swaps_filtered_by_status(create_db_pool):
    """Test getting swaps filtered by status"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/swaps", json=swap_data)

            # Get pending swaps
            response = await client.get("/api/swaps?status=pending")
            assert response.status_code == 200
            data = response.json()
            assert all(swap["status"] == "pending" for swap in data["swaps"])


async def test_get_specific_swap(create_db_pool):
    """Test getting a specific swap by ID"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create swap
            create_response = await client.post("/api/swaps", json=swap_data)
            swap_id = create_response.json()["swapId"]

            # Get specific swap
            response = await client.get(f"/api/swaps/{swap_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["swapId"] == swap_id
            assert data["userAUid"] == user_a_uid
            assert data["userBUid"] == user_b_uid


async def test_get_swap_unauthorized(create_db_pool):
    """Test that unauthorized users cannot view a swap"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_c_uid = uuid4().hex[:20]  # Not part of the swap
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)
    user_c_uid = await add_user(create_db_pool, uid=user_c_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    swap_id = None
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post("/api/swaps", json=swap_data)
            swap_id = create_response.json()["swapId"]

    # Try to access as user C
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_c_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/swaps/{swap_id}")
            assert response.status_code == 403
            assert "Not authorized" in response.json()["detail"]


async def test_accept_swap(create_db_pool):
    """Test accepting a swap (user B accepts)"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    swap_id = None
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post("/api/swaps", json=swap_data)
            swap_id = create_response.json()["swapId"]

    # User B accepts
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_b_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/swaps/{swap_id}/accept")
            assert response.status_code == 200
            assert "accepted" in response.json()["message"]

            # Verify status changed
            swap = await create_db_pool.fetchrow(
                "SELECT status FROM swaps WHERE swap_id = $1", swap_id
            )
            assert swap["status"] == "accepted"


async def test_accept_swap_only_user_b(create_db_pool):
    """Test that only user B can accept the swap"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    swap_id = None
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post("/api/swaps", json=swap_data)
            swap_id = create_response.json()["swapId"]

            # User A tries to accept (should fail)
            response = await client.post(f"/api/swaps/{swap_id}/accept")
            assert response.status_code == 403
            assert "recipient" in response.json()["detail"]


async def test_decline_swap(create_db_pool):
    """Test declining a swap"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    swap_id = None
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post("/api/swaps", json=swap_data)
            swap_id = create_response.json()["swapId"]

    # User B declines
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_b_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/swaps/{swap_id}/decline",
                json={"cancellationReason": "Not interested anymore"}
            )
            assert response.status_code == 200
            assert "declined" in response.json()["message"]

            # Verify status changed
            swap = await create_db_pool.fetchrow(
                "SELECT status, cancellation_reason FROM swaps WHERE swap_id = $1", swap_id
            )
            assert swap["status"] == "cancelled"
            assert swap["cancellation_reason"] == "Not interested anymore"


async def test_confirm_receipt_both_users(create_db_pool):
    """Test confirming receipt by both users completes the swap"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    swap_id = None
    # Create and accept swap
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post("/api/swaps", json=swap_data)
            swap_id = create_response.json()["swapId"]

    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_b_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(f"/api/swaps/{swap_id}/accept")

    # User A confirms receipt
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/swaps/{swap_id}/confirm-receipt")
            assert response.status_code == 200
            assert "Waiting for other party" in response.json()["message"]

            # Verify user_a_confirmed is True
            swap = await create_db_pool.fetchrow(
                "SELECT user_a_confirmed, user_b_confirmed, status FROM swaps WHERE swap_id = $1", swap_id
            )
            assert swap["user_a_confirmed"] is True
            assert swap["user_b_confirmed"] is False
            assert swap["status"] == "accepted"

    # User B confirms receipt
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_b_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/swaps/{swap_id}/confirm-receipt")
            assert response.status_code == 200
            assert "completed" in response.json()["message"]

            # Verify swap is completed
            swap = await create_db_pool.fetchrow(
                "SELECT user_a_confirmed, user_b_confirmed, status FROM swaps WHERE swap_id = $1", swap_id
            )
            assert swap["user_a_confirmed"] is True
            assert swap["user_b_confirmed"] is True
            assert swap["status"] == "completed"


async def test_confirm_receipt_requires_accepted_status(create_db_pool):
    """Test that confirming receipt requires swap to be accepted first"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    swap_id = None
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post("/api/swaps", json=swap_data)
            swap_id = create_response.json()["swapId"]

            # Try to confirm receipt while still pending
            response = await client.post(f"/api/swaps/{swap_id}/confirm-receipt")
            assert response.status_code == 400
            assert "must be accepted" in response.json()["detail"]


async def test_cancel_swap(create_db_pool):
    """Test cancelling a swap"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    swap_data = {
        "userBUid": user_b_uid,
        "listingAId": listing_a_id,
        "listingBId": listing_b_id,
        "listingACategory": "books",
        "listingBCategory": "books",
    }

    swap_id = None
    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post("/api/swaps", json=swap_data)
            swap_id = create_response.json()["swapId"]

            # User A cancels
            response = await client.post(
                f"/api/swaps/{swap_id}/cancel",
                json={"cancellationReason": "Changed my mind"}
            )
            assert response.status_code == 200
            assert "cancelled" in response.json()["message"]

            # Verify status changed
            swap = await create_db_pool.fetchrow(
                "SELECT status, cancelled_by, cancellation_reason FROM swaps WHERE swap_id = $1", swap_id
            )
            assert swap["status"] == "cancelled"
            assert swap["cancelled_by"] == user_a_uid
            assert swap["cancellation_reason"] == "Changed my mind"


async def test_cannot_cancel_completed_swap(create_db_pool):
    """Test that completed swaps cannot be cancelled"""
    app.state.limiter.enabled = False

    user_a_uid = uuid4().hex[:20]
    user_b_uid = uuid4().hex[:20]
    user_a_uid = await add_user(create_db_pool, uid=user_a_uid)
    user_b_uid = await add_user(create_db_pool, uid=user_b_uid)

    listing_a_id = await add_listing(create_db_pool, user_a_uid, "books")
    listing_b_id = await add_listing(create_db_pool, user_b_uid, "books")

    # Create swap directly in database as completed
    swap_id = str(uuid4())
    await create_db_pool.execute(
        """
        INSERT INTO swaps (swap_id, user_a_uid, user_b_uid, listing_a_id, listing_b_id,
                          category, status, user_a_confirmed, user_b_confirmed)
        VALUES ($1, $2, $3, $4, $5, 'books', 'completed', TRUE, TRUE)
        """,
        swap_id, user_a_uid, user_b_uid, listing_a_id, listing_b_id
    )

    with patch("app.api.swaps.extract_firebase_user_uid", return_value=user_a_uid):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/swaps/{swap_id}/cancel",
                json={"cancellationReason": "Test"}
            )
            assert response.status_code == 400
            assert "Cannot cancel completed swap" in response.json()["detail"]
