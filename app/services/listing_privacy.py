"""
Decides who may see a home's exact location and a host's full identity.

Default is private. Exact location and full identity are revealed only to the
owner and to the other side of an accepted swap, and any failed check stays private.

"Accepted" lives in two places, and both count:
  - swap_chains/swap_legs in Postgres (the swap API)
  - conversations in Firestore (the inbox accept button)
"""

import asyncio
import logging

from firebase_admin import firestore

from app.middleware import auth  # noqa: F401 - initialises Firebase before the Firestore client

logger = logging.getLogger(__name__)

# Copies of the owner's details on listing rows. Never returned with a listing:
# /users/{uid} is the one place that decides who sees them.
OWNER_DETAIL_FIELDS = frozenset({"email", "name", "profile_image"})
EXACT_LOCATION_FIELDS = frozenset({"street_address", "postal_code", "latitude", "longitude"})
PRIVATE_LISTING_FIELDS = OWNER_DETAIL_FIELDS | EXACT_LOCATION_FIELDS

_REVEALING_CHAIN_STATUSES = ["accepted", "completed"]

_conversations_db = firestore.client(database_id="firestore-messages-databases")


def strip_private_listing_fields(listing: dict) -> dict:
    return {key: value for key, value in listing.items() if key not in PRIVATE_LISTING_FIELDS}


def first_name_only(name: str | None) -> str | None:
    parts = name.split() if name else []
    return parts[0] if parts else None


def _accepted_conversations(viewer_uid: str) -> list[dict]:
    conversations = (
        _conversations_db.collection("conversations")
        .where("participants", "array_contains", viewer_uid)
        .stream()
    )
    accepted = []
    for conversation in conversations:
        data = conversation.to_dict()
        if data.get("status") == "accepted":
            accepted.append(data)
    return accepted


async def _safe_accepted_conversations(viewer_uid: str) -> list[dict]:
    try:
        return await asyncio.to_thread(_accepted_conversations, viewer_uid)
    except Exception as e:
        logger.error(f"Could not read conversations, keeping data private: {type(e).__name__}: {e}")
        return []


async def can_view_exact_location(
    conn, viewer_uid: str | None, listing_id: str, owner_uid: str
) -> bool:
    """True for the owner, or for whoever receives this listing in an accepted swap."""
    if viewer_uid is None:
        return False
    if viewer_uid == owner_uid:
        return True

    # from_user must be the owner: conversation and leg data can name any listing,
    # so a swap between two other accounts must not unlock someone else's home.
    in_accepted_chain = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM swap_legs l
            JOIN swap_chains c ON c.chain_id = l.chain_id
            WHERE l.listing_id = $1::uuid
              AND l.from_user = $2
              AND l.to_user = $3
              AND c.status = ANY($4)
        )
        """,
        listing_id,
        owner_uid,
        viewer_uid,
        _REVEALING_CHAIN_STATUSES,
    )
    if in_accepted_chain:
        return True

    for conversation in await _safe_accepted_conversations(viewer_uid):
        viewer_is_requester = (
            conversation.get("requester_uid") == viewer_uid
            and conversation.get("recipient_uid") == owner_uid
            and conversation.get("recipient_listing_id") == listing_id
        )
        viewer_is_recipient = (
            conversation.get("recipient_uid") == viewer_uid
            and conversation.get("requester_uid") == owner_uid
            and conversation.get("requester_listing_id") == listing_id
        )
        if viewer_is_requester or viewer_is_recipient:
            return True
    return False


async def can_view_full_identity(conn, viewer_uid: str | None, subject_uid: str) -> bool:
    """True for the user themselves, or for someone they have an accepted swap with."""
    if viewer_uid is None:
        return False
    if viewer_uid == subject_uid:
        return True

    # Both must have agreed as givers, so nobody can unlock a stranger by naming
    # them as the receiver in a chain they never accepted.
    in_accepted_chain = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM swap_chains c
            JOIN swap_legs viewer_leg ON viewer_leg.chain_id = c.chain_id
            JOIN swap_legs subject_leg ON subject_leg.chain_id = c.chain_id
            WHERE c.status = ANY($3)
              AND viewer_leg.from_user = $1 AND viewer_leg.accepted
              AND subject_leg.from_user = $2 AND subject_leg.accepted
        )
        """,
        viewer_uid,
        subject_uid,
        _REVEALING_CHAIN_STATUSES,
    )
    if in_accepted_chain:
        return True

    return any(
        subject_uid in conversation.get("participants", [])
        for conversation in await _safe_accepted_conversations(viewer_uid)
    )
