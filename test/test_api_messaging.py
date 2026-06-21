"""
Real integration tests for messaging API using Firebase Firestore Emulator.
No mocking - uses actual Firestore instance (locally).
"""

from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

from firebase_admin import firestore
from httpx import ASGITransport, AsyncClient

from app.main import app

# Initialize Firestore client (will connect to emulator via FIRESTORE_EMULATOR_HOST env var)
db = firestore.client(database_id="firestore-messages-databases")


# ============================================
# HELPER FUNCTIONS
# ============================================


async def cleanup_firestore():
    """Delete all conversations and messages from Firestore emulator"""
    # Delete all conversations
    conversations = db.collection("conversations").stream()
    for conv in conversations:
        # Delete all messages in this conversation
        messages = conv.reference.collection("messages").stream()
        for msg in messages:
            msg.reference.delete()
        # Delete conversation
        conv.reference.delete()


async def create_test_conversation(requester_uid: str, recipient_uid: str) -> str:
    """Helper to create a test conversation directly in Firestore"""
    conversation_data = {
        "participants": [requester_uid, recipient_uid],
        "requester_uid": requester_uid,
        "recipient_uid": recipient_uid,
        "last_message": "Test message",
        "last_message_at": firestore.SERVER_TIMESTAMP,
        "unread_count_requester": 0,
        "unread_count_recipient": 1,
        "created_at": firestore.SERVER_TIMESTAMP,
        "status": "pending",
    }

    conv_ref = db.collection("conversations").document()
    conv_ref.set(conversation_data)
    return conv_ref.id


# ============================================
# TESTS - CREATE CONVERSATION
# ============================================


async def test_create_conversation_success(create_db_pool):
    """Test successfully creating a new conversation in real Firestore"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    requester_uid = uuid4().hex[:20]
    recipient_uid = uuid4().hex[:20]

    conversation_data = {
        "recipientUid": recipient_uid,
        "initialMessage": "Hello, I'm interested in your listing!",
        "requesterListingId": str(uuid4()),
        "recipientListingId": str(uuid4()),
        "requesterListingCategory": "books",
        "recipientListingCategory": "books",
    }

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=requester_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/messaging/conversations", json=conversation_data)

            assert response.status_code == 200
            data = response.json()
            assert "conversationId" in data
            conv_id = data["conversationId"]

            # Verify conversation exists in Firestore
            conv_ref = db.collection("conversations").document(conv_id)
            conv_doc = conv_ref.get()
            assert conv_doc.exists
            conv_data = conv_doc.to_dict()
            assert requester_uid in conv_data["participants"]
            assert recipient_uid in conv_data["participants"]
            assert conv_data["status"] == "pending"

            # Verify initial message exists in Firestore
            messages = list(conv_ref.collection("messages").stream())
            assert len(messages) == 1
            msg_data = messages[0].to_dict()
            assert msg_data["text"] == "Hello, I'm interested in your listing!"
            assert msg_data["sender_uid"] == requester_uid
            assert msg_data["receiver_uid"] == recipient_uid


async def test_create_conversation_with_existing_conversation(create_db_pool):
    """Test sending message to existing conversation"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    requester_uid = uuid4().hex[:20]
    recipient_uid = uuid4().hex[:20]
    requester_listing_id = str(uuid4())
    recipient_listing_id = str(uuid4())

    # Create first conversation
    conversation_data = {
        "recipientUid": recipient_uid,
        "initialMessage": "First message",
        "requesterListingId": requester_listing_id,
        "recipientListingId": recipient_listing_id,
        "requesterListingCategory": "books",
        "recipientListingCategory": "books",
    }

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=requester_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create conversation
            response1 = await client.post("/api/messaging/conversations", json=conversation_data)
            assert response1.status_code == 200
            conv_id = response1.json()["conversationId"]

            # Send another message (should use same conversation)
            conversation_data["initialMessage"] = "Second message"
            response2 = await client.post("/api/messaging/conversations", json=conversation_data)
            assert response2.status_code == 200
            assert response2.json()["conversationId"] == conv_id
            assert response2.json()["message"] == "Message sent"

            # Verify 2 messages exist
            messages = list(
                db.collection("conversations").document(conv_id).collection("messages").stream()
            )
            assert len(messages) == 2


async def test_create_conversation_with_self_fails(create_db_pool):
    """Test that creating a conversation with yourself fails"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]

    conversation_data = {
        "recipientUid": user_uid,  # Same as requester
        "initialMessage": "Hello!",
    }

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/messaging/conversations", json=conversation_data)

            assert response.status_code == 400
            assert "Cannot message yourself" in response.json()["detail"]

            # Verify no conversation was created
            conversations = list(db.collection("conversations").stream())
            assert len(conversations) == 0


async def test_create_conversation_xss_prevention(create_db_pool):
    """Test that XSS attempts in messages are blocked"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    requester_uid = uuid4().hex[:20]
    recipient_uid = uuid4().hex[:20]

    conversation_data = {
        "recipientUid": recipient_uid,
        "initialMessage": "<script>alert('xss')</script>",
    }

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=requester_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/messaging/conversations", json=conversation_data)

            # Should fail validation
            assert response.status_code == 422

            # Verify no conversation was created
            conversations = list(db.collection("conversations").stream())
            assert len(conversations) == 0


# ============================================
# TESTS - GET CONVERSATIONS
# ============================================


async def test_get_conversations_success(create_db_pool):
    """Test getting all conversations for a user"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]
    other_uid_1 = uuid4().hex[:20]
    other_uid_2 = uuid4().hex[:20]

    # Create 2 conversations for user
    conv_id_1 = await create_test_conversation(user_uid, other_uid_1)
    conv_id_2 = await create_test_conversation(user_uid, other_uid_2)

    # Create conversation not involving user
    await create_test_conversation(other_uid_1, other_uid_2)

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/messaging/conversations")

            assert response.status_code == 200
            data = response.json()
            assert "conversations" in data
            assert data["total"] == 2

            # Verify correct conversations returned
            conv_ids = [conv["conversationId"] for conv in data["conversations"]]
            assert conv_id_1 in conv_ids
            assert conv_id_2 in conv_ids


async def test_get_conversations_empty(create_db_pool):
    """Test getting conversations when user has none"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]

    # Create conversation not involving user
    await create_test_conversation(uuid4().hex[:20], uuid4().hex[:20])

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/messaging/conversations")

            assert response.status_code == 200
            data = response.json()
            assert data["conversations"] == []
            assert data["total"] == 0


# ============================================
# TESTS - GET MESSAGES
# ============================================


async def test_get_messages_success(create_db_pool):
    """Test getting messages for a conversation"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]
    other_uid = uuid4().hex[:20]

    # Create conversation
    conv_id = await create_test_conversation(user_uid, other_uid)

    # Add some messages
    conv_ref = db.collection("conversations").document(conv_id)
    conv_ref.collection("messages").add(
        {
            "sender_uid": user_uid,
            "receiver_uid": other_uid,
            "text": "Message 1",
            "created_at": firestore.SERVER_TIMESTAMP,
            "is_read": False,
        }
    )
    conv_ref.collection("messages").add(
        {
            "sender_uid": other_uid,
            "receiver_uid": user_uid,
            "text": "Message 2",
            "created_at": firestore.SERVER_TIMESTAMP,
            "is_read": False,
        }
    )

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/messaging/conversations/{conv_id}/messages")

            assert response.status_code == 200
            data = response.json()
            assert "messages" in data
            assert data["total"] == 2
            assert len(data["messages"]) == 2


async def test_get_messages_unauthorized_user(create_db_pool):
    """Test that unauthorized users cannot view conversation messages"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]  # Not part of conversation
    other_uid_1 = uuid4().hex[:20]
    other_uid_2 = uuid4().hex[:20]

    # Create conversation between other users
    conv_id = await create_test_conversation(other_uid_1, other_uid_2)

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/messaging/conversations/{conv_id}/messages")

            assert response.status_code == 403
            assert "Not a participant" in response.json()["detail"]


# ============================================
# TESTS - SEND MESSAGE
# ============================================


async def test_send_message_text_only(create_db_pool):
    """Test sending a text-only message"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]
    other_uid = uuid4().hex[:20]

    # Create conversation
    conv_id = await create_test_conversation(user_uid, other_uid)

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/messaging/conversations/{conv_id}/messages",
                data={"text": "Hello there!"},
            )

            assert response.status_code == 200
            assert "sent" in response.json()["message"]

            # Verify message exists in Firestore
            messages = list(
                db.collection("conversations")
                .document(conv_id)
                .collection("messages")
                .stream()
            )
            assert len(messages) == 1
            msg_data = messages[0].to_dict()
            assert msg_data["text"] == "Hello there!"
            assert msg_data["sender_uid"] == user_uid
            assert msg_data["receiver_uid"] == other_uid


async def test_send_message_requires_content(create_db_pool):
    """Test that sending a message requires either text or media"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]
    other_uid = uuid4().hex[:20]

    conv_id = await create_test_conversation(user_uid, other_uid)

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/messaging/conversations/{conv_id}/messages",
                data={"text": ""},  # Empty text
            )

            assert response.status_code == 400
            assert "text or media" in response.json()["detail"]

            # Verify no message was created
            messages = list(
                db.collection("conversations")
                .document(conv_id)
                .collection("messages")
                .stream()
            )
            assert len(messages) == 0


async def test_send_message_not_participant(create_db_pool):
    """Test that non-participants cannot send messages"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]  # Not part of conversation
    other_uid_1 = uuid4().hex[:20]
    other_uid_2 = uuid4().hex[:20]

    # Create conversation between other users
    conv_id = await create_test_conversation(other_uid_1, other_uid_2)

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/messaging/conversations/{conv_id}/messages",
                data={"text": "Hello!"},
            )

            assert response.status_code == 403
            assert "Not a participant" in response.json()["detail"]


# ============================================
# TESTS - MARK MESSAGES AS READ
# ============================================


async def test_mark_messages_as_read_success(create_db_pool):
    """Test marking messages as read"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]
    other_uid = uuid4().hex[:20]

    # Create conversation
    conv_id = await create_test_conversation(user_uid, other_uid)

    # Add unread messages for user
    conv_ref = db.collection("conversations").document(conv_id)
    conv_ref.collection("messages").add(
        {
            "sender_uid": other_uid,
            "receiver_uid": user_uid,
            "text": "Message 1",
            "created_at": firestore.SERVER_TIMESTAMP,
            "is_read": False,
        }
    )
    conv_ref.collection("messages").add(
        {
            "sender_uid": other_uid,
            "receiver_uid": user_uid,
            "text": "Message 2",
            "created_at": firestore.SERVER_TIMESTAMP,
            "is_read": False,
        }
    )

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(f"/api/messaging/conversations/{conv_id}/read")

            assert response.status_code == 200
            assert "marked" in response.json()["message"].lower()

            # Verify messages are marked as read in Firestore
            messages = conv_ref.collection("messages").where("receiver_uid", "==", user_uid).stream()
            for msg in messages:
                msg_data = msg.to_dict()
                assert msg_data["is_read"] is True
                assert "read_at" in msg_data


# ============================================
# TESTS - UPDATE CONVERSATION STATUS
# ============================================


async def test_update_conversation_status_accept(create_db_pool):
    """Test accepting a swap request"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    requester_uid = uuid4().hex[:20]
    recipient_uid = uuid4().hex[:20]

    conv_id = await create_test_conversation(requester_uid, recipient_uid)

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=recipient_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.patch(
                f"/api/messaging/conversations/{conv_id}/status",
                json={"status": "accepted"},
            )

            assert response.status_code == 200
            assert "accepted" in response.json()["message"]

            # Verify status updated in Firestore
            conv_doc = db.collection("conversations").document(conv_id).get()
            assert conv_doc.to_dict()["status"] == "accepted"


async def test_update_conversation_status_only_recipient(create_db_pool):
    """Test that only the recipient (host) can accept/decline"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    requester_uid = uuid4().hex[:20]
    recipient_uid = uuid4().hex[:20]

    conv_id = await create_test_conversation(requester_uid, recipient_uid)

    # Requester tries to accept (should fail)
    with patch("app.api.messaging.extract_firebase_user_uid", return_value=requester_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.patch(
                f"/api/messaging/conversations/{conv_id}/status",
                json={"status": "accepted"},
            )

            assert response.status_code == 403
            assert "host" in response.json()["detail"]

            # Verify status unchanged
            conv_doc = db.collection("conversations").document(conv_id).get()
            assert conv_doc.to_dict()["status"] == "pending"


# ============================================
# TESTS - DELETE CONVERSATION
# ============================================


async def test_delete_conversation_success(create_db_pool):
    """Test deleting a conversation and all its messages"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]
    other_uid = uuid4().hex[:20]

    # Create conversation with messages
    conv_id = await create_test_conversation(user_uid, other_uid)
    conv_ref = db.collection("conversations").document(conv_id)
    conv_ref.collection("messages").add({"text": "Message 1"})
    conv_ref.collection("messages").add({"text": "Message 2"})

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.delete(f"/api/messaging/conversations/{conv_id}")

            assert response.status_code == 200
            assert "deleted" in response.json()["message"].lower()
            assert response.json()["deletedMessages"] == 2

            # Verify conversation deleted from Firestore
            conv_doc = db.collection("conversations").document(conv_id).get()
            assert not conv_doc.exists

            # Verify messages deleted
            messages = list(conv_ref.collection("messages").stream())
            assert len(messages) == 0


async def test_delete_conversation_unauthorized(create_db_pool):
    """Test that only participants can delete a conversation"""
    await cleanup_firestore()
    app.state.limiter.enabled = False

    user_uid = uuid4().hex[:20]  # Not a participant
    other_uid_1 = uuid4().hex[:20]
    other_uid_2 = uuid4().hex[:20]

    # Create conversation between other users
    conv_id = await create_test_conversation(other_uid_1, other_uid_2)

    with patch("app.api.messaging.extract_firebase_user_uid", return_value=user_uid):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.delete(f"/api/messaging/conversations/{conv_id}")

            assert response.status_code == 403
            assert "Not a participant" in response.json()["detail"]

            # Verify conversation still exists
            conv_doc = db.collection("conversations").document(conv_id).get()
            assert conv_doc.exists
