"""
Unified swap engine built on swap_chains + swap_legs.

A swap is one chain (the deal) + N legs (each item handoff). A direct 2-person
swap is simply a chain with 2 legs, so this one engine handles direct AND
multi-way (3+) swaps - there is no separate 2-party path.

Lifecycle (swap_chains.status):
    pending   -> proposed; waiting for every GIVER to accept their leg
    accepted  -> all givers accepted; items are exchanged in real life
    completed -> every RECEIVER confirmed receipt; ownership transferred
    cancelled -> someone declined / cancelled before completion

Per leg:
    accepted  -> the from_user (giver) agreed to the swap
    received  -> the to_user (receiver) confirmed they got the item

All functions take an asyncpg connection; the API layer owns the pool. Multi-step
operations open their own transaction so they are atomic.
"""

import logging

from app.constants import LISTING_CATEGORIES
from app.services.swap_chain_finder import SwapChain, SwapEdge, find_swap_chains

logger = logging.getLogger(__name__)

# Statuses that still hold an item hostage (so it can't join another chain).
ACTIVE_STATUSES = ("pending", "accepted")


async def listings_already_in_active_chain(conn, listing_ids: list[str]) -> set[str]:
    """Return the subset of listing_ids that are already part of a pending/accepted chain."""
    if not listing_ids:
        return set()
    rows = await conn.fetch(
        """
        SELECT DISTINCT l.listing_id
        FROM swap_legs l
        JOIN swap_chains c ON c.chain_id = l.chain_id
        WHERE l.listing_id = ANY($1::uuid[]) AND c.status = ANY($2)
        """,
        listing_ids,
        list(ACTIVE_STATUSES),
    )
    return {str(r["listing_id"]) for r in rows}


async def find_suggested_chains(conn, user_uid: str, max_length: int = 3) -> list[dict]:
    """
    System-discovered swaps: build the giver->wanter graph from wishlist_matches,
    find 2- and 3-way loops, and return the ones that involve this user and whose
    items aren't already locked in another active chain. These are SUGGESTIONS -
    nothing is created until the user proposes one.
    """
    rows = await conn.fetch(
        """
        SELECT giver_firebase_uid, wanter_firebase_uid, listing_id, category
        FROM wishlist_matches
        WHERE giver_firebase_uid IS NOT NULL
        """
    )
    # edge: the listing's owner (giver) hands listing to the wishlist owner (wanter)
    edges = [
        SwapEdge(
            from_user=r["giver_firebase_uid"],
            to_user=r["wanter_firebase_uid"],
            listing_id=str(r["listing_id"]),
            category=r["category"],
        )
        for r in rows
    ]

    chains = find_swap_chains(edges, max_length=max_length)

    suggestions: list[dict] = []
    for chain in chains:
        if user_uid not in chain.participants:
            continue
        listing_ids = [leg.listing_id for leg in chain.legs]
        if await listings_already_in_active_chain(conn, listing_ids):
            continue  # an item is already tied up; not a live suggestion
        suggestions.append(_serialize_found_chain(chain))
    return suggestions


def _serialize_found_chain(chain: SwapChain) -> dict:
    """A not-yet-created chain (suggestion) as a serialisable dict."""
    return {
        "length": chain.length,
        "participants": sorted(chain.participants),
        "legs": [
            {
                "from_user": leg.from_user,
                "to_user": leg.to_user,
                "listing_id": leg.listing_id,
                "category": leg.category,
            }
            for leg in chain.legs
        ],
    }


async def get_listing_owner(conn, category: str, listing_id: str) -> str | None:
    """Owner uid of a listing, or None if it doesn't exist. Validates the category."""
    if category not in LISTING_CATEGORIES:
        raise ValueError(f"Unknown category: {category}")
    # category checked against the allowlist, safe to interpolate as a table name
    return await conn.fetchval(
        f"SELECT owner_firebase_uid FROM {category} WHERE listing_id = $1", listing_id
    )


async def propose_chain(
    conn,
    legs: list[SwapEdge],
    conversation_id: str | None = None,
    auto_accept_from_user: str | None = None,
) -> dict:
    """
    Create a pending chain from a set of legs (a found cycle, or a direct request).
    Fails if any listing is already locked in another active chain (prevents
    double-booking the same item).

    auto_accept_from_user: if set, that user's leg starts already accepted - used
    for direct requests, where the initiator has implicitly agreed by proposing.
    """
    if len(legs) < 2:
        raise ValueError("A swap chain needs at least 2 legs")

    listing_ids = [leg.listing_id for leg in legs]

    async with conn.transaction():
        locked = await listings_already_in_active_chain(conn, listing_ids)
        if locked:
            raise ValueError(f"Listings already in an active swap: {locked}")

        chain_row = await conn.fetchrow(
            """
            INSERT INTO swap_chains (status, conversation_id)
            VALUES ('pending', $1)
            RETURNING chain_id, status, conversation_id, created_at
            """,
            conversation_id,
        )
        chain_id = chain_row["chain_id"]

        await conn.executemany(
            """
            INSERT INTO swap_legs (chain_id, from_user, to_user, listing_id, category)
            VALUES ($1, $2, $3, $4, $5)
            """,
            [(chain_id, leg.from_user, leg.to_user, leg.listing_id, leg.category) for leg in legs],
        )

        if auto_accept_from_user:
            await conn.execute(
                """
                UPDATE swap_legs SET accepted = TRUE, accepted_at = NOW()
                WHERE chain_id = $1 AND from_user = $2
                """,
                chain_id,
                auto_accept_from_user,
            )

        logger.info(f"Proposed chain {chain_id} with {len(legs)} legs")
        return await _chain_detail(conn, chain_id)


async def propose_suggested_chain(conn, user_uid: str, legs: list[SwapEdge]) -> dict:
    """
    Materialise a suggested chain into a real pending chain. Validates that the
    requesting user is actually a participant and that every leg's giver really
    owns the listing (so a client can't fabricate legs). The requesting user's
    leg is pre-accepted.
    """
    participants = {leg.from_user for leg in legs} | {leg.to_user for leg in legs}
    if user_uid not in participants:
        raise PermissionError("You are not part of this swap")

    for leg in legs:
        owner = await get_listing_owner(conn, leg.category, leg.listing_id)
        if owner is None:
            raise LookupError(f"Listing {leg.listing_id} not found")
        if owner != leg.from_user:
            raise ValueError(f"Listing {leg.listing_id} is not owned by {leg.from_user}")

    return await propose_chain(conn, legs, auto_accept_from_user=user_uid)


async def accept_chain(conn, chain_id: str, user_uid: str) -> dict:
    """
    The user (a GIVER) accepts their leg. When every leg is accepted, the chain
    flips to 'accepted'.
    """
    async with conn.transaction():
        await _assert_status(conn, chain_id, "pending")

        result = await conn.execute(
            """
            UPDATE swap_legs SET accepted = TRUE, accepted_at = NOW()
            WHERE chain_id = $1 AND from_user = $2 AND accepted = FALSE
            """,
            chain_id,
            user_uid,
        )
        if result == "UPDATE 0":
            raise PermissionError("You are not a giver in this swap, or already accepted")

        if await _all_legs(conn, chain_id, "accepted"):
            await conn.execute(
                "UPDATE swap_chains SET status = 'accepted', updated_at = NOW() WHERE chain_id = $1",
                chain_id,
            )
            logger.info(f"Chain {chain_id} fully accepted")

        return await _chain_detail(conn, chain_id)


async def confirm_receipt(conn, chain_id: str, user_uid: str) -> dict:
    """
    The user (a RECEIVER) confirms they got their item. When every receiver has
    confirmed, the chain completes and ownership transfers.
    """
    async with conn.transaction():
        await _assert_status(conn, chain_id, "accepted")

        result = await conn.execute(
            """
            UPDATE swap_legs SET received = TRUE, received_at = NOW()
            WHERE chain_id = $1 AND to_user = $2 AND received = FALSE
            """,
            chain_id,
            user_uid,
        )
        if result == "UPDATE 0":
            raise PermissionError("You are not a receiver in this swap, or already confirmed")

        if await _all_legs(conn, chain_id, "received"):
            await _transfer_ownership(conn, chain_id)
            await conn.execute(
                "UPDATE swap_chains SET status = 'completed', completed_at = NOW(), updated_at = NOW() WHERE chain_id = $1",
                chain_id,
            )
            logger.info(f"Chain {chain_id} completed; ownership transferred")

        return await _chain_detail(conn, chain_id)


async def cancel_chain(conn, chain_id: str, user_uid: str) -> dict:
    """Any participant cancels/declines a chain that hasn't completed yet."""
    async with conn.transaction():
        chain = await conn.fetchrow("SELECT status FROM swap_chains WHERE chain_id = $1", chain_id)
        if not chain:
            raise LookupError("Swap not found")
        if chain["status"] in ("completed", "cancelled"):
            raise ValueError(f"Cannot cancel a {chain['status']} swap")
        if not await _is_participant(conn, chain_id, user_uid):
            raise PermissionError("You are not a participant in this swap")

        await conn.execute(
            """
            UPDATE swap_chains
            SET status = 'cancelled', cancelled_at = NOW(), cancelled_by = $2, updated_at = NOW()
            WHERE chain_id = $1
            """,
            chain_id,
            user_uid,
        )
        logger.info(f"Chain {chain_id} cancelled by {user_uid}")
        return await _chain_detail(conn, chain_id)


async def get_user_chains(conn, user_uid: str, status: str | None = None) -> list[dict]:
    """All chains the user participates in (as giver or receiver), newest first."""
    query = """
        SELECT DISTINCT c.chain_id
        FROM swap_chains c
        JOIN swap_legs l ON l.chain_id = c.chain_id
        WHERE (l.from_user = $1 OR l.to_user = $1)
    """
    params = [user_uid]
    if status:
        query += " AND c.status = $2"
        params.append(status)

    rows = await conn.fetch(query, *params)
    chains = [await _chain_detail(conn, r["chain_id"]) for r in rows]
    chains.sort(key=lambda c: c["created_at"], reverse=True)
    return chains


async def get_chain(conn, chain_id: str, user_uid: str) -> dict:
    """One chain's detail, only if the user participates in it."""
    if not await _is_participant(conn, chain_id, user_uid):
        raise PermissionError("You are not a participant in this swap")
    return await _chain_detail(conn, chain_id)


# --- internals ---------------------------------------------------------------

async def _transfer_ownership(conn, chain_id: str) -> None:
    """For each leg, move the listing (and its image rows) from giver to receiver."""
    legs = await conn.fetch(
        "SELECT from_user, to_user, listing_id, category FROM swap_legs WHERE chain_id = $1",
        chain_id,
    )
    for leg in legs:
        category = leg["category"]
        if category not in LISTING_CATEGORIES:
            raise ValueError(f"Unknown category on leg: {category}")
        # category is validated against the allowlist, safe to interpolate as a table name
        await conn.execute(
            f"UPDATE {category} SET owner_firebase_uid = $1, status = 'swapped', updated_at = NOW() WHERE listing_id = $2",
            leg["to_user"],
            leg["listing_id"],
        )
        # keep the denormalized owner on images in sync with the listing
        await conn.execute(
            "UPDATE images SET owner_firebase_uid = $1, updated_at = NOW() WHERE listing_id = $2",
            leg["to_user"],
            leg["listing_id"],
        )


async def _all_legs(conn, chain_id: str, flag: str) -> bool:
    """True if every leg of the chain has the given boolean flag set (accepted/received)."""
    remaining = await conn.fetchval(
        f"SELECT COUNT(*) FROM swap_legs WHERE chain_id = $1 AND {flag} = FALSE",
        chain_id,
    )
    return remaining == 0


async def _is_participant(conn, chain_id: str, user_uid: str) -> bool:
    found = await conn.fetchval(
        "SELECT 1 FROM swap_legs WHERE chain_id = $1 AND (from_user = $2 OR to_user = $2) LIMIT 1",
        chain_id,
        user_uid,
    )
    return found is not None


async def _assert_status(conn, chain_id: str, expected: str) -> None:
    status = await conn.fetchval("SELECT status FROM swap_chains WHERE chain_id = $1", chain_id)
    if status is None:
        raise LookupError("Swap not found")
    if status != expected:
        raise ValueError(f"Swap must be '{expected}' for this action (currently '{status}')")


async def _chain_detail(conn, chain_id: str) -> dict:
    """Assemble a chain + its legs into a serialisable dict."""
    chain = await conn.fetchrow(
        """
        SELECT chain_id, status, conversation_id, created_at, updated_at, completed_at, cancelled_at, cancelled_by
        FROM swap_chains WHERE chain_id = $1
        """,
        chain_id,
    )
    legs = await conn.fetch(
        """
        SELECT leg_id, from_user, to_user, listing_id, category, accepted, accepted_at, received, received_at
        FROM swap_legs WHERE chain_id = $1 ORDER BY created_at
        """,
        chain_id,
    )

    def iso(v):
        return v.isoformat() if v else None

    return {
        "chain_id": str(chain["chain_id"]),
        "status": chain["status"],
        "conversation_id": chain["conversation_id"],
        "created_at": iso(chain["created_at"]),
        "updated_at": iso(chain["updated_at"]),
        "completed_at": iso(chain["completed_at"]),
        "cancelled_at": iso(chain["cancelled_at"]),
        "cancelled_by": chain["cancelled_by"],
        "legs": [
            {
                "leg_id": str(leg["leg_id"]),
                "from_user": leg["from_user"],
                "to_user": leg["to_user"],
                "listing_id": str(leg["listing_id"]),
                "category": leg["category"],
                "accepted": leg["accepted"],
                "accepted_at": iso(leg["accepted_at"]),
                "received": leg["received"],
                "received_at": iso(leg["received_at"]),
            }
            for leg in legs
        ],
    }
