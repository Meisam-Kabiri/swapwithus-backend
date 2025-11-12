from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app
from test.factories import UserCreateFactory


def test_create_user(create_db_pool):
    user_data = UserCreateFactory.build()

    # Mock Firebase auth verification
    with patch('app.main.verify_firebase_token') as mock_verify:
        mock_verify.return_value = user_data.owner_firebase_uid

        # Use TestClient with context manager (triggers lifespan)
        # we can choose not to use context manager cuz we are create the pool in the fixture manually
        with TestClient(app) as client:
            # Disable rate limiting for tests by setting enabled=False
            app.state.limiter.enabled = False

            response = client.post("/api/users", json=user_data.model_dump())

            assert response.status_code == 201
            data = response.json()
            assert data.get("uid") == user_data.owner_firebase_uid
            assert data.get("message") == "User created successfully"


from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport
async def test_create_user_async(create_db_pool):  # Use db_pool fixture
    user_data = UserCreateFactory.build()

    with patch('app.main.verify_firebase_token') as mock_verify:
        mock_verify.return_value = user_data.owner_firebase_uid

        app.state.limiter.enabled = False

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/users", json=user_data.model_dump())

            assert response.status_code == 201
            data = response.json()
            assert data.get("uid") == user_data.owner_firebase_uid

            # BONUS: Verify it's actually in the database!
            async with create_db_pool.acquire() as conn:
                user = await conn.fetchrow(
                    "SELECT * FROM users WHERE owner_firebase_uid = $1",
                    user_data.owner_firebase_uid
                )
                assert user is not None
                assert user["email"] == user_data.email
                assert user["name"] == user_data.name


        # you can also use client = AsyncClient(..) and not use async with statement
        # but then you have to remember to call await client.aclose() at the end of the test

      