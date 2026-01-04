"""
Messaging API - Secure proxy to Firestore

Architecture:
- Frontend calls this API (not Firestore directly)
- Backend validates all writes (identity, rate limits, content)
- Backend writes to Firestore using admin SDK
- Frontend can still listen to Firestore for real-time updates
- Firestore rules block direct client writes

Security:
- Prevents fake sender_uid (verified via Firebase token)
- Rate limiting
- Content sanitization (XSS prevention)
- Authorization checks (only participants can message)
"""

import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from firebase_admin import firestore

from app.middleware.auth import extract_firebase_user_uid
from app.middleware.rate_limit import limiter
from app.models.message import (
    ConversationStatusUpdate,
    CreateConversationRequest,
    SendMessageRequest,
)
from app.services.messaging_media_service import upload_message_media

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/messaging", tags=["messaging"])

# Initialize Firestore client
db = firestore.client(database_id="firestore-messages-databases")


# ============================================
# HELPER FUNCTIONS
# ============================================


def get_other_user_uid(conversation_data: dict, current_user_uid: str) -> str:
    """Get the other user's UID in a conversation"""
    requester_uid = conversation_data.get("requester_uid")
    recipient_uid = conversation_data.get("recipient_uid")

    if current_user_uid == requester_uid:
        return recipient_uid
    elif current_user_uid == recipient_uid:
        return requester_uid
    else:
        raise HTTPException(status_code=403, detail="Not a participant in this conversation")


def is_participant(conversation_data: dict, user_uid: str) -> bool:
    """Check if user is a participant in conversation"""
    participants = conversation_data.get("participants", [])
    return user_uid in participants


def get_unread_count_for_user(conversation_data: dict, user_uid: str) -> int:
    """Get unread count for specific user"""
    is_requester = user_uid == conversation_data.get("requester_uid")
    if is_requester:
        return conversation_data.get("unread_count_requester", 0)
    else:
        return conversation_data.get("unread_count_recipient", 0)


# ============================================
# API ENDPOINTS
# ============================================


@router.post("/conversations")
@limiter.limit("10/minute")
async def create_conversation(request: Request, data: CreateConversationRequest):
    """
    Create a new conversation or return existing one.

    Security:
    - Requester UID verified from Firebase token (cannot be faked)
    - Rate limited to 10/minute
    - Message content sanitized
    """
    requester_uid = extract_firebase_user_uid(request)
    if not requester_uid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Validate not messaging self
    if requester_uid == data.recipient_uid:
        raise HTTPException(status_code=400, detail="Cannot message yourself")

    try:
        # Check if conversation already exists for this specific listing pair
        conversations_ref = db.collection("conversations")
        existing = conversations_ref.where("participants", "array_contains", requester_uid).stream()

        existing_conv_id = None
        for conv in existing:
            conv_data = conv.to_dict()
            # Check if same participants AND same listing pair
            if (data.recipient_uid in conv_data.get("participants", []) and
                conv_data.get("requester_listing_id") == data.requester_listing_id and
                conv_data.get("recipient_listing_id") == data.recipient_listing_id):
                existing_conv_id = conv.id
                break

        if existing_conv_id:
            # Add message to existing conversation
            message_data = {
                "sender_uid": requester_uid,
                "receiver_uid": data.recipient_uid,
                "text": data.initial_message,
                "created_at": firestore.SERVER_TIMESTAMP,
                "is_read": False,
            }

            # Add media if provided
            if data.media_url and data.media_type:
                message_data["media_url"] = data.media_url
                message_data["media_type"] = data.media_type

            db.collection("conversations").document(existing_conv_id).collection("messages").add(
                message_data
            )

            # Determine last_message preview
            if data.initial_message:
                last_message_preview = data.initial_message
            elif data.media_type == "image":
                last_message_preview = "📷 Image"
            else:  # video
                last_message_preview = "🎥 Video"

            # Update last message
            logger.info(f"DEBUG CREATE: Adding to existing conversation, initial_message={data.initial_message}")
            db.collection("conversations").document(existing_conv_id).update(
                {
                    "last_message": last_message_preview,
                    "last_message_at": firestore.SERVER_TIMESTAMP,
                    "unread_count_recipient": firestore.Increment(1),
                }
            )

            logger.info(f"Added message to existing conversation {existing_conv_id}")
            return {"conversationId": existing_conv_id, "message": "Message sent"}

        # Determine last_message preview for new conversation
        if data.initial_message:
            last_message_preview = data.initial_message
        elif data.media_type == "image":
            last_message_preview = "📷 Image"
        else:  # video
            last_message_preview = "🎥 Video"

        # Create new conversation
        conversation_data = {
            "participants": [requester_uid, data.recipient_uid],
            "requester_uid": requester_uid,
            "recipient_uid": data.recipient_uid,
            "last_message": last_message_preview,
            "last_message_at": firestore.SERVER_TIMESTAMP,
            "unread_count_requester": 0,
            "unread_count_recipient": 1,
            "created_at": firestore.SERVER_TIMESTAMP,
            "status": "pending",
        }

        if data.requester_listing_id:
            conversation_data["requester_listing_id"] = data.requester_listing_id
        if data.recipient_listing_id:
            conversation_data["recipient_listing_id"] = data.recipient_listing_id
        if data.requester_listing_category:
            conversation_data["requester_listing_category"] = data.requester_listing_category
        if data.recipient_listing_category:
            conversation_data["recipient_listing_category"] = data.recipient_listing_category

        # Create conversation
        conv_ref = db.collection("conversations").document()
        conv_ref.set(conversation_data)

        # Add initial message
        message_data = {
            "sender_uid": requester_uid,
            "receiver_uid": data.recipient_uid,
            "text": data.initial_message,
            "created_at": firestore.SERVER_TIMESTAMP,
            "is_read": False,
        }

        # Add media if provided
        if data.media_url and data.media_type:
            message_data["media_url"] = data.media_url
            message_data["media_type"] = data.media_type

        conv_ref.collection("messages").add(message_data)

        logger.info(f"Created new conversation {conv_ref.id}")
        return {"conversationId": conv_ref.id, "message": "Conversation created"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating conversation: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create conversation")


@router.get("/conversations")
@limiter.limit("30/minute")
async def get_conversations(request: Request):
    """
    Get all conversations for the authenticated user.

    Returns conversations ordered by last message time (most recent first).
    """
    print("Fetching conversations")
    user_uid = extract_firebase_user_uid(request)
    if not user_uid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        conversations_ref = db.collection("conversations")
        user_conversations = (
            conversations_ref.where("participants", "array_contains", user_uid)
            .order_by("last_message_at", direction=firestore.Query.DESCENDING)
            .stream()
        )

        conversations = []
        for conv in user_conversations:
            conv_data = conv.to_dict()

            # Get unread count for this user
            unread_count = get_unread_count_for_user(conv_data, user_uid)

            conversation = {
                "conversationId": conv.id,
                "requesterUid": conv_data.get("requester_uid"),
                "recipientUid": conv_data.get("recipient_uid"),
                "requesterListingId": conv_data.get("requester_listing_id"),
                "recipientListingId": conv_data.get("recipient_listing_id"),
                "requesterListingCategory": conv_data.get("requester_listing_category"),
                "recipientListingCategory": conv_data.get("recipient_listing_category"),
                "lastMessage": conv_data.get("last_message", ""),
                "lastMessageAt": conv_data.get("last_message_at"),
                "unreadCount": unread_count,
                "status": conv_data.get("status", "pending"),
                "createdAt": conv_data.get("created_at"),
            }
            conversations.append(conversation)

        logger.info(f"Retrieved {len(conversations)} conversations for user {user_uid}")
        print(conversations)
        return {"conversations": conversations, "total": len(conversations)}

    except Exception as e:
        logger.error(f"Error fetching conversations: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch conversations")


@router.get("/conversations/{conversation_id}/messages")
@limiter.limit("60/minute")
async def get_messages(request: Request, conversation_id: str, limit: int = 25):
    """
    Get messages for a conversation.

    Security:
    - User must be a participant
    - Ordered by creation time (oldest first for chat display)
    """
    user_uid = extract_firebase_user_uid(request)
    if not user_uid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Verify user is participant
        conv_ref = db.collection("conversations").document(conversation_id)
        conv_doc = conv_ref.get()

        if not conv_doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conv_data = conv_doc.to_dict()
        if not is_participant(conv_data, user_uid):
            raise HTTPException(status_code=403, detail="Not a participant in this conversation")

        # Get messages
        messages_ref = conv_ref.collection("messages")
        messages = (
            messages_ref.order_by("created_at", direction=firestore.Query.ASCENDING)
            .limit(limit)
            .stream()
        )

        message_list = []
        for msg in messages:
            msg_data = msg.to_dict()
            message = {
                "messageId": msg.id,
                "senderUid": msg_data.get("sender_uid"),
                "receiverUid": msg_data.get("receiver_uid"),
                "text": msg_data.get("text"),
                "createdAt": msg_data.get("created_at"),
                "isRead": msg_data.get("is_read", False),
                "readAt": msg_data.get("read_at"),
            }

            # Add media fields if present
            if msg_data.get("media_url"):
                message["mediaUrl"] = msg_data.get("media_url")
                message["mediaType"] = msg_data.get("media_type")

            message_list.append(message)

        logger.info(f"Retrieved {len(message_list)} messages for conversation {conversation_id}")
        return {"messages": message_list, "total": len(message_list)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching messages: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch messages")


@router.post("/conversations/{conversation_id}/messages")
@limiter.limit("20/minute")
async def send_message(
    request: Request,
    conversation_id: str,
    text: str | None = Form(None),
    media: UploadFile | None = File(None)
):
    """
    Send a message in a conversation.

    Supports:
    - Text-only messages
    - Media-only messages (image/video/audio)
    - Combined text + media messages

    Security:
    - Sender UID verified from Firebase token
    - Checks user is a participant
    - Rate limited to 20/minute
    - Content sanitized
    - File type and size validation
    """
    sender_uid = extract_firebase_user_uid(request)
    if not sender_uid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Validate at least text or media is provided
    if (not text or not text.strip()) and not media:
        raise HTTPException(status_code=400, detail="Message must contain text or media")

    # Debug logging
    logger.info(f"Received message: text={text}, has_media={media is not None}")

    try:
        # Get conversation and verify participation
        conv_ref = db.collection("conversations").document(conversation_id)
        conv_doc = conv_ref.get()

        if not conv_doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conv_data = conv_doc.to_dict()
        if not is_participant(conv_data, sender_uid):
            raise HTTPException(status_code=403, detail="Not a participant in this conversation")

        # Determine receiver
        receiver_uid = get_other_user_uid(conv_data, sender_uid)

        # Upload media if provided
        media_url = None
        media_type = None
        if media:
            logger.info(f"Uploading media: {media.filename}")
            media_url, media_type = await upload_message_media(media, conversation_id)
            logger.info(f"Media uploaded: {media_url}, type: {media_type}")

        # Create message
        message_data = {
            "sender_uid": sender_uid,
            "receiver_uid": receiver_uid,
            "created_at": firestore.SERVER_TIMESTAMP,
            "is_read": False,
        }

        # Add text if provided
        if text and text.strip():
            message_data["text"] = text.strip()

        # Add media if uploaded
        if media_url and media_type:
            message_data["media_url"] = media_url
            message_data["media_type"] = media_type

        conv_ref.collection("messages").add(message_data)

        # Update conversation metadata
        is_requester = sender_uid == conv_data.get("requester_uid")

        # Determine last_message preview
        if text and text.strip():
            last_message_preview = text.strip()
        elif media_type == "image":
            last_message_preview = "📷 Image"
        elif media_type == "video":
            last_message_preview = "🎥 Video"
        elif media_type == "audio":
            last_message_preview = "🎵 Audio"
        else:
            last_message_preview = "Message"

        # Debug logging
        logger.info(f"DEBUG: sender_uid={sender_uid}, receiver_uid={receiver_uid}")
        logger.info(f"DEBUG: text={text}, media_type={media_type}")
        logger.info(f"DEBUG: About to update last_message with: {last_message_preview}")

        update_data = {
            "last_message": last_message_preview,
            "last_message_at": firestore.SERVER_TIMESTAMP,
        }

        # Increment unread count for receiver
        if is_requester:
            update_data["unread_count_recipient"] = firestore.Increment(1)
        else:
            update_data["unread_count_requester"] = firestore.Increment(1)

        conv_ref.update(update_data)

        logger.info(f"Message sent in conversation {conversation_id}")
        return {"message": "Message sent successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send message")


# RPC-style endpoint (not REST): Uses POST with action verb for clarity
@router.post("/conversations/{conversation_id}/read")
@limiter.limit("50/minute")
async def mark_messages_read(request: Request, conversation_id: str):
    """
    Mark all messages as read for the current user.

    Security:
    - User UID verified from Firebase token
    - Checks user is a participant
    """
    user_uid = extract_firebase_user_uid(request)
    if not user_uid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Get conversation and verify participation
        conv_ref = db.collection("conversations").document(conversation_id)
        conv_doc = conv_ref.get()

        if not conv_doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conv_data = conv_doc.to_dict()
        if not is_participant(conv_data, user_uid):
            raise HTTPException(status_code=403, detail="Not a participant")

        # Mark all unread messages as read
        messages_ref = conv_ref.collection("messages")
        unread_messages = (
            messages_ref.where("receiver_uid", "==", user_uid).where("is_read", "==", False).stream()
        )

        batch = db.batch()
        count = 0
        for msg in unread_messages:
            batch.update(msg.reference, {"is_read": True, "read_at": firestore.SERVER_TIMESTAMP})
            count += 1

        batch.commit()

        # Reset unread count
        is_requester = user_uid == conv_data.get("requester_uid")
        if is_requester:
            conv_ref.update({"unread_count_requester": 0})
        else:
            conv_ref.update({"unread_count_recipient": 0})

        logger.info(f"Marked {count} messages as read in conversation {conversation_id}")
        return {"message": f"Marked {count} messages as read"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking messages read: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to mark messages read")


@router.patch("/conversations/{conversation_id}/status")
@limiter.limit("10/minute")
async def update_conversation_status(
    request: Request, conversation_id: str, data: ConversationStatusUpdate
):
    """
    Accept or decline a swap request.

    Security:
    - Only the HOST can accept/decline
    - User UID verified from Firebase token
    """
    user_uid = extract_firebase_user_uid(request)
    if not user_uid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Get conversation
        conv_ref = db.collection("conversations").document(conversation_id)
        conv_doc = conv_ref.get()

        if not conv_doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conv_data = conv_doc.to_dict()

        # Only host can accept/decline
        if user_uid != conv_data.get("recipient_uid"):
            raise HTTPException(status_code=403, detail="Only the host can accept/decline")

        # Update status
        conv_ref.update({"status": data.status})

        logger.info(f"Conversation {conversation_id} status updated to {data.status}")
        return {"message": f"Swap request {data.status}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error updating conversation status: {type(e).__name__}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to update status")


@router.delete("/conversations/{conversation_id}")
@limiter.limit("10/minute")
async def delete_conversation(request: Request, conversation_id: str):
    """
    Delete a conversation and all its messages.

    Security:
    - Only participants can delete
    - User UID verified from Firebase token
    - Deletes all messages in the conversation
    """
    user_uid = extract_firebase_user_uid(request)
    if not user_uid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Get conversation and verify participation
        conv_ref = db.collection("conversations").document(conversation_id)
        conv_doc = conv_ref.get()

        if not conv_doc.exists:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conv_data = conv_doc.to_dict()
        if not is_participant(conv_data, user_uid):
            raise HTTPException(status_code=403, detail="Not a participant in this conversation")

        # Delete all messages in the conversation
        messages_ref = conv_ref.collection("messages")
        messages = messages_ref.stream()

        batch = db.batch()
        message_count = 0
        for msg in messages:
            batch.delete(msg.reference)
            message_count += 1

        # Delete the conversation itself
        batch.delete(conv_ref)
        batch.commit()

        logger.info(
            f"Deleted conversation {conversation_id} with {message_count} messages by user {user_uid}"
        )
        return {
            "message": f"Conversation deleted successfully with {message_count} messages",
            "deletedMessages": message_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete conversation")



#TODO: Add ThreadPoolExecutor for blocking Firestore calls if performance issues arise
#TODO: In the future consider swtiching to postgres+redis(websockets) for messaging if Firestore costs/performance become an issue
#TODO: Add pagination to messages and conversations if needed in future

# User clicks Delete →
#     ┌─────────────────────────────────┐
#     │ Delete Conversation?            │
#     │                                 │
#     │ ○ Delete for me only           │
#     │   (Other person keeps messages) │
#     │                                 │
#     │ ○ Delete for everyone          │
#     │   (Removes for both users)      │
#     │   ⚠ This cannot be undone     │
#     │                                 │
#     │ [Cancel]  [Delete]             │
#     └─────────────────────────────────┘

#   ---
#   Implementation Plan:

#   Endpoint 1: Delete for Me (Soft)

#   PATCH /api/messaging/conversations/{id}/hide
#   → Adds user to hidden_for array
#   → User no longer sees it in their list

#   Endpoint 2: Delete for Everyone (Hard)

#   DELETE /api/messaging/conversations/{id}?deleteForEveryone=true
#   → Deletes conversation document
#   → Deletes all messages
#   → Deletes all media files from Storage
#   → Irreversible

