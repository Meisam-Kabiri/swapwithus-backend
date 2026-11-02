from test.factories import UserCreateFactory
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.auth import FirebaseUser, get_firebase_user


async def test_create_user(create_db_pool):
    user_data = UserCreateFactory.build()
    email = f"{uuid4().hex}@example.com"
    app.dependency_overrides[get_firebase_user] = lambda: FirebaseUser(
        user_data.owner_firebase_uid, email, True
    )
    app.state.limiter.enabled = False

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/users", json=user_data.model_dump())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201, response.text
    data = response.json()
    assert data.get("uid") == user_data.owner_firebase_uid
    assert data.get("message") == "User created successfully"

    user = await create_db_pool.fetchrow(
        "SELECT * FROM users WHERE owner_firebase_uid = $1",
        user_data.owner_firebase_uid,
    )
    assert user is not None
    assert user["email"] == email
    assert user["name"] == user_data.name
