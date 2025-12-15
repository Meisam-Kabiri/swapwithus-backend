from httpx import AsyncClient
from app.main import app
# from factories import SwapCreateFactory
import pytest
from httpx import ASGITransport
from unittest.mock import patch

# Make sure the database contains at least two users and two listings before running swap tests
# If there is no, you can create them using the create users test api and create listing test api

async def test_create_swap_for_books(create_db_pool):

  app.state.limiter.enabled = False
  # Extract two listings from database for two different users
  async with create_db_pool.acquire() as conn:
    listings = await conn.fetch("""
      SELECT * FROM books
      WHERE owner_firebase_uid IN (
        SELECT DISTINCT owner_firebase_uid FROM books LIMIT 2
      )
      LIMIT 2
    """)
    listing1 = dict(listings[0])
    listing2 = dict(listings[1])

    # Clean up any existing swaps for these listings to avoid duplicate errors
    await conn.execute(
      """DELETE FROM swaps
         WHERE (listing_a_id = $1 AND listing_b_id = $2)
            OR (listing_a_id = $2 AND listing_b_id = $1)""",
      listing1["listing_id"],
      listing2["listing_id"]
    )

    swapdata = {
        # "user_a_uid": listing1["owner_firebase_uid"],
        "user_b_uid": str(listing2["owner_firebase_uid"]),
        "listing_a_id": str(listing1["listing_id"]),
        "listing_b_id": str(listing2["listing_id"]),
        "listing_a_category": "books",
        "listing_b_category": "books",
        "conversation_id": None
    }
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
      with patch("app.api.swaps.extract_firebase_user_uid") as mock_verify:
        mock_verify.return_value = str(listing1["owner_firebase_uid"])
        response = await client.post("/api/swaps", json=swapdata)

        # Verify response status (201 = Created)
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()

        # Verify swap was created with correct data
        assert data.get("swapId") is not None, "Swap ID should be present"
        swap_id = data.get("swapId")
        assert data.get("status") == "pending", "New swap should have pending status"

        # API returns camelCase fields
        assert data.get("listingAId") == str(listing1["listing_id"])
        assert data.get("listingBId") == str(listing2["listing_id"])
        assert data.get("userAUid") == str(listing1["owner_firebase_uid"])
        assert data.get("userBUid") == str(listing2["owner_firebase_uid"])
        assert data.get("category") == "books"

        # Verify swap was saved to database
        db_swap = await conn.fetchrow(
          "SELECT * FROM swaps WHERE swap_id = $1",
          swap_id
        )
        assert db_swap is not None, "Swap should be saved in database"
        assert str(db_swap["listing_a_id"]) == str(listing1["listing_id"])
        assert str(db_swap["listing_b_id"]) == str(listing2["listing_id"])

        # Note: Swap is kept in database for dev testing and subsequent tests
        
    
async def test_get_all_my_swaps(create_db_pool):
    app.state.limiter.enabled = False

    # Extract a user from database who has at least one swap
    async with create_db_pool.acquire() as conn:
        user = await conn.fetchrow("""
            SELECT * FROM swaps LIMIT 1
        """)
        print(user)
        user_uid = str(user["user_a_uid"])
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("app.api.swaps.extract_firebase_user_uid") as mock_verify:
                mock_verify.return_value = user_uid
                response = await client.get("/api/swaps")

                # Verify response status
                assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
                data = response.json() #convert json response to python dict

                # Verify response structure
                assert "swaps" in data, "Response should contain 'swaps' key"
                swaps = data["swaps"]
                assert isinstance(swaps, list), "Swaps should be a list"
                assert len(swaps) > 0, "User should have at least one swap"

                # Verify each swap involves the user
                for swap in swaps:
                    assert swap.get("userAUid") == user_uid or swap.get("userBUid") == user_uid

async def test_get_swap_by_id(create_db_pool):
    app.state.limiter.enabled = False

    # Extract a swap from database
    async with create_db_pool.acquire() as conn:
        swap = await conn.fetchrow("""
            SELECT * FROM swaps LIMIT 1
        """)
        swap_id = str(swap["swap_id"])
        user_uid = str(swap["user_a_uid"])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("app.api.swaps.extract_firebase_user_uid") as mock_verify:
                mock_verify.return_value = user_uid
                response = await client.get(f"/api/swaps/{swap_id}")

                # Verify response status
                assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
                data = response.json()

                # Verify returned swap data
                assert data.get("swapId") == swap_id, "Returned swap ID should match requested ID"
                assert data.get("userAUid") == user_uid or data.get("userBUid") == user_uid, "User should be part of the swap"
                
async def test_accept_swap(create_db_pool):
    app.state.limiter.enabled = False

    # Extract a pending swap from database
    async with create_db_pool.acquire() as conn:
        swap = await conn.fetchrow("""
            SELECT * FROM swaps WHERE status = 'pending' LIMIT 1
        """)
        if swap is None:
            await conn.execute("""UPDATE swaps
              SET status = 'pending'
              WHERE swap_id = (
                  SELECT swap_id
                  FROM swaps
                  ORDER BY random()
                  LIMIT 1
              );
                          """)
        swap = await conn.fetchrow("""
            SELECT * FROM swaps WHERE status = 'pending' LIMIT 1
        """)
            
        swap_id = str(swap["swap_id"])
        user_b_uid = str(swap["user_b_uid"])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("app.api.swaps.extract_firebase_user_uid") as mock_verify:
                mock_verify.return_value = user_b_uid
                response = await client.patch(f"/api/swaps/{swap_id}/accept")

                # Verify response status
                assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
                data = response.json()

                # Verify success message
                assert data.get("message") == "Swap accepted successfully", "Should return success message"

                # Verify swap status in database
                db_swap = await conn.fetchrow(
                    "SELECT * FROM swaps WHERE swap_id = $1",
                    swap_id
                )
                assert db_swap["status"] == "accepted", "Swap status in database should be accepted"
                assert db_swap["accepted_at"] is not None, "Accepted timestamp should be set"
                
async def test_decline_swap(create_db_pool):
    app.state.limiter.enabled = False

    # Extract a pending swap from database
    async with create_db_pool.acquire() as conn:
        swap = await conn.fetchrow("""
            SELECT * FROM swaps WHERE status = 'pending' LIMIT 1
        """)
        if swap is None:
            await conn.execute("""UPDATE swaps
              SET status = 'pending'
              WHERE swap_id = (
                  SELECT swap_id
                  FROM swaps
                  ORDER BY random()
                  LIMIT 1
              );

                          """)
            swap = await conn.fetchrow("""
                SELECT * FROM swaps WHERE status = 'pending' LIMIT 1
            """)
            
        swap_id = str(swap["swap_id"])
        user_b_uid = str(swap["user_b_uid"])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("app.api.swaps.extract_firebase_user_uid") as mock_verify:
                mock_verify.return_value = user_b_uid
                response = await client.patch(
                    f"/api/swaps/{swap_id}/decline",
                    json={"cancellationReason": "Not interested"}
                )

                # Verify response status
                assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
                data = response.json()

                # Verify success message
                assert data.get("message") == "Swap declined successfully", "Should return success message"

                # Verify swap status in database
                db_swap = await conn.fetchrow(
                    "SELECT * FROM swaps WHERE swap_id = $1",
                    swap_id
                )
                assert db_swap["status"] == "cancelled", "Swap status in database should be cancelled"
                assert db_swap["cancelled_at"] is not None, "Cancelled timestamp should be set"
                
async def test_confirm_receipt(create_db_pool):
    app.state.limiter.enabled = False

    # Extract an accepted swap from database
    async with create_db_pool.acquire() as conn:
        swap = await conn.fetchrow("""
            SELECT * FROM swaps WHERE status = 'accepted' LIMIT 1
        """)
        if swap is None:
            await conn.execute("""UPDATE swaps
              SET status = 'accepted', user_a_confirmed = FALSE, user_b_confirmed = FALSE
              WHERE swap_id = (
                  SELECT swap_id
                  FROM swaps
                  ORDER BY random()
                  LIMIT 1
              );

                          """)
        swap = await conn.fetchrow("""
            SELECT * FROM swaps WHERE status = 'accepted' LIMIT 1
        """)

        # Reset confirmation flags for testing
        await conn.execute("""
            UPDATE swaps
            SET user_a_confirmed = FALSE, user_b_confirmed = FALSE
            WHERE swap_id = $1
        """, swap["swap_id"])
        swap_id = str(swap["swap_id"])
        user_a_uid = str(swap["user_a_uid"])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("app.api.swaps.extract_firebase_user_uid") as mock_verify:
                mock_verify.return_value = user_a_uid
                response = await client.post(f"/api/swaps/{swap_id}/confirm-receipt")

                # Verify response status
                assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
                data = response.json()

                # Verify success message
                assert data.get("message") == "Receipt confirmed. Waiting for other party to confirm.", "Should return success message"

                # Verify user_a_confirmed in database
                db_swap = await conn.fetchrow(
                    "SELECT * FROM swaps WHERE swap_id = $1",
                    swap_id
                )
                assert db_swap["user_a_confirmed"] is True, "user_a_confirmed should be True"
                
async def test_cancel_swaps(create_db_pool):
    app.state.limiter.enabled = False

    # Extract a pending swap from database
    async with create_db_pool.acquire() as conn:
        swap = await conn.fetchrow("""
            SELECT * FROM swaps WHERE status = 'pending' LIMIT 1
        """)
        if swap is None:
            await conn.execute("""UPDATE swaps
              SET status = 'pending'
              WHERE swap_id = (
                  SELECT swap_id
                  FROM swaps
                  ORDER BY random()
                  LIMIT 1
              );

                          """)
            swap = await conn.fetchrow("""
                SELECT * FROM swaps WHERE status = 'pending' LIMIT 1
            """)
            
        swap_id = str(swap["swap_id"])
        user_a_uid = str(swap["user_a_uid"])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("app.api.swaps.extract_firebase_user_uid") as mock_verify:
                mock_verify.return_value = user_a_uid
                response = await client.patch(
                    f"/api/swaps/{swap_id}/cancel",
                    json={"cancellationReason": "Change of mind"}
                )

                # Verify response status
                assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
                data = response.json()

                # Verify success message
                assert data.get("message") == "Swap cancelled successfully", "Should return success message"

                # Verify swap status in database
                db_swap = await conn.fetchrow(
                    "SELECT * FROM swaps WHERE swap_id = $1",
                    swap_id
                )
                assert db_swap["status"] == "cancelled", "Swap status in database should be cancelled"
                assert db_swap["cancelled_at"] is not None, "Cancelled timestamp should be set"