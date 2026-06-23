"""
Matches newly created listings against active wishlists.

Kept deliberately simple (Python-side keyword/filter checks against a small
per-category candidate set) rather than building search infrastructure -
wishlist volume per category is expected to be modest.
"""

import json
import logging

from app.constants import SEARCHABLE_FIELDS_BY_CATEGORY

logger = logging.getLogger(__name__)


def _build_searchable_text(category: str, listing_data: dict) -> str:
    fields = SEARCHABLE_FIELDS_BY_CATEGORY.get(category, [])
    parts = []
    for field in fields:
        value = listing_data.get(field)
        if not value:
            continue
        if isinstance(value, list):
            parts.append(" ".join(str(v) for v in value))
        else:
            parts.append(str(value))
    return " ".join(parts).lower()


def _wishlist_matches_listing(searchable_text: str, listing_data: dict, keywords: list[str], filters: dict) -> bool:
    if keywords and any(kw in searchable_text for kw in keywords):
        return True

    if filters:
        return all(str(listing_data.get(key, "")).lower() == str(value).lower() for key, value in filters.items())

    return False


async def match_new_listing_against_wishlists(conn, category: str, listing_data: dict) -> int:
    """
    Find active wishlists (excluding the listing owner's own) that match the
    newly created listing, and record them in wishlist_matches.

    Must be called with the listing's owner_firebase_uid and listing_id already
    present in listing_data. Returns the number of new matches recorded.
    """
    # TODO(scale): unbounded fan-out for popular items. One listing for a hot item
    # (e.g. "guitar") matches EVERY active wishlist wanting it, so a single post can:
    #   1. fetch thousands of candidate wishlists into Python memory (the query below),
    #   2. write thousands of wishlist_matches rows in one executemany.
    # It's not a correctness bug (each row is a valid match), but it's O(wishlists in
    # category) per listing post and will hurt once any category gets popular. When that
    # happens, move this off the request path (queue/Cloud Tasks worker), cap/paginate
    # the candidate set, and/or push matching into SQL with a real index instead of
    # loading every wishlist. Fine for now at low volume - left intentionally simple.
    owner_uid = listing_data.get("owner_firebase_uid")
    listing_id = listing_data.get("listing_id")
    if not owner_uid or not listing_id:
        return 0

    candidates = await conn.fetch(
        """
        SELECT wishlist_id, owner_firebase_uid, keywords, filters
        FROM wishlists
        WHERE category = $1 AND status = 'active' AND owner_firebase_uid != $2
        """,
        category,
        owner_uid,
    )

    if not candidates:
        return 0

    searchable_text = _build_searchable_text(category, listing_data)

    matched_wishlist_ids = []
    matched_owner_uids = []
    for row in candidates:
        filters = row["filters"]
        if isinstance(filters, str):
            filters = json.loads(filters)

        if _wishlist_matches_listing(searchable_text, listing_data, row["keywords"] or [], filters or {}):
            matched_wishlist_ids.append(row["wishlist_id"])
            matched_owner_uids.append(row["owner_firebase_uid"])

    if not matched_wishlist_ids:
        return 0

    await conn.executemany(
        """
        INSERT INTO wishlist_matches
            (wishlist_id, listing_id, category, wanter_firebase_uid, giver_firebase_uid)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (wishlist_id, listing_id) DO NOTHING
        """,
        [
            # wanter_uid = the WANTER (wishlist owner); owner_uid = the GIVER (listing owner)
            (wishlist_id, listing_id, category, wanter_uid, owner_uid)
            for wishlist_id, wanter_uid in zip(matched_wishlist_ids, matched_owner_uids)
        ],
    )

    logger.info(f"Listing {listing_id} ({category}) matched {len(matched_wishlist_ids)} wishlist(s)")
    return len(matched_wishlist_ids)
