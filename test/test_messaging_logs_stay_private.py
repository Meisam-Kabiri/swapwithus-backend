import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.auth import extract_firebase_user_uid

SECRET = "my-private-phone-0401234567"
SECRET_FILENAME = "my-private-passport.jpg"
SECRET_MEDIA_URL = "https://storage.test/signed?token=my-private-signature"
SENDER = "sender_uid"
RECEIVER = "receiver_uid"


def conversation_doc():
    doc = MagicMock(id="conversation_1", exists=True)
    doc.to_dict.return_value = {
        "participants": [SENDER, RECEIVER],
        "requester_uid": SENDER,
        "recipient_uid": RECEIVER,
        "status": "pending",
        "last_message": SECRET,
    }
    return doc


@pytest.fixture
def firestore_db():
    app.state.limiter.enabled = False
    app.dependency_overrides[extract_firebase_user_uid] = lambda: SENDER
    db = MagicMock()
    conversations = db.collection.return_value
    conversations.document.return_value.get.return_value = conversation_doc()
    conversations.where.return_value.stream.return_value = [conversation_doc()]
    conversations.where.return_value.order_by.return_value.stream.return_value = [conversation_doc()]
    with patch("app.api.messaging.db", db):
        yield db
    app.dependency_overrides.clear()


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def assert_nothing_private_logged(caplog, capsys):
    captured = capsys.readouterr()
    output = caplog.text + captured.out + captured.err
    for private_value in (SECRET, SECRET_FILENAME, SECRET_MEDIA_URL):
        assert private_value not in output


async def test_sending_a_message_does_not_log_its_text(firestore_db, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    async with client() as c:
        response = await c.post("/api/messaging/conversations/conversation_1/messages", data={"text": SECRET})

    assert response.status_code == 200, response.text
    assert_nothing_private_logged(caplog, capsys)


async def test_sending_media_does_not_log_its_name_or_link(firestore_db, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    upload = AsyncMock(return_value=(SECRET_MEDIA_URL, "image"))
    with patch("app.api.messaging.upload_message_media", new=upload):
        async with client() as c:
            response = await c.post(
                "/api/messaging/conversations/conversation_1/messages",
                files={"media": (SECRET_FILENAME, b"x", "image/jpeg")},
            )

    assert response.status_code == 200, response.text
    assert_nothing_private_logged(caplog, capsys)


async def test_listing_conversations_does_not_log_them(firestore_db, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    async with client() as c:
        response = await c.get("/api/messaging/conversations")

    assert response.status_code == 200, response.text
    assert SECRET in response.text  # The user still receives it, it just isn't logged
    assert_nothing_private_logged(caplog, capsys)


async def test_adding_to_a_conversation_does_not_log_the_message(firestore_db, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    async with client() as c:
        response = await c.post(
            "/api/messaging/conversations",
            json={"recipientUid": RECEIVER, "initialMessage": SECRET},
        )

    assert response.status_code == 200, response.text
    assert_nothing_private_logged(caplog, capsys)
