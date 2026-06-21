import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database.connection import get_pool_from_request
from app.middleware.auth import extract_firebase_user_uid
from app.middleware.rate_limit import limiter
from app.models.wishlist import WishlistCreate, WishlistUpdate

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/wishlists", tags=["wishlists"])


def snake_to_camel_dict(data):
    """Convert snake_case keys to camelCase in dict"""
    if not isinstance(data, dict):
        return data

    result = {}
    for key, value in data.items():
        parts = key.split('_')
        camel_key = parts[0] + ''.join(word.capitalize() for word in parts[1:])
        result[camel_key] = value
    return result


@router.post("")
@limiter.limit("20/hour")
async def create_wishlist(request: Request, wishlist: WishlistCreate):
    """Create a new wishlist entry for the authenticated user."""
    uid = extract_firebase_user_uid(request)

    if not wishlist.keywords and not wishlist.filters:
        raise HTTPException(status_code=400, detail="Provide at least one keyword or filter")

    try:
        async with get_pool_from_request(request).acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO wishlists (owner_firebase_uid, category, keywords, filters)
                VALUES ($1, $2, $3, $4)
                RETURNING wishlist_id, owner_firebase_uid, category, keywords, filters,
                          status, created_at, updated_at
                """,
                uid,
                wishlist.category,
                wishlist.keywords,
                wishlist.filters,
            )

            result = dict(row)
            result["wishlist_id"] = str(result["wishlist_id"])
            result["created_at"] = result["created_at"].isoformat()
            result["updated_at"] = result["updated_at"].isoformat()

            logger.info(f"User {uid} created wishlist {result['wishlist_id']} for category {wishlist.category}")
            return JSONResponse(status_code=201, content=snake_to_camel_dict(result))

    except Exception as e:
        logger.error(f"Error creating wishlist: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create wishlist. Please try again.")


@router.get("")
@limiter.limit("60/minute")
async def get_my_wishlists(request: Request):
    """List all wishlists belonging to the authenticated user."""
    uid = extract_firebase_user_uid(request)

    try:
        async with get_pool_from_request(request).acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT wishlist_id, owner_firebase_uid, category, keywords, filters,
                       status, created_at, updated_at
                FROM wishlists
                WHERE owner_firebase_uid = $1
                ORDER BY created_at DESC
                """,
                uid,
            )

            wishlists = []
            for row in rows:
                item = dict(row)
                item["wishlist_id"] = str(item["wishlist_id"])
                item["created_at"] = item["created_at"].isoformat()
                item["updated_at"] = item["updated_at"].isoformat()
                wishlists.append(snake_to_camel_dict(item))

            return JSONResponse(status_code=200, content={"wishlists": wishlists})

    except Exception as e:
        logger.error(f"Error fetching wishlists for user {uid}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch wishlists. Please try again.")


@router.patch("/{wishlist_id}")
@limiter.limit("30/hour")
async def update_wishlist(request: Request, wishlist_id: str, wishlist_update: WishlistUpdate):
    """Update keywords, filters, or status of one of the authenticated user's wishlists."""
    uid = extract_firebase_user_uid(request)

    update_fields = wishlist_update.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    set_clauses = []
    values = []
    for index, (field, value) in enumerate(update_fields.items(), start=1):
        set_clauses.append(f"{field} = ${index}")
        values.append(value)

    query = f"""
        UPDATE wishlists
        SET {', '.join(set_clauses)}, updated_at = NOW()
        WHERE wishlist_id = ${len(values) + 1} AND owner_firebase_uid = ${len(values) + 2}
        RETURNING wishlist_id, owner_firebase_uid, category, keywords, filters, status, created_at, updated_at
    """
    values.extend([wishlist_id, uid])

    try:
        async with get_pool_from_request(request).acquire() as conn:
            row = await conn.fetchrow(query, *values)

            if not row:
                raise HTTPException(status_code=404, detail="Wishlist not found")

            result = dict(row)
            result["wishlist_id"] = str(result["wishlist_id"])
            result["created_at"] = result["created_at"].isoformat()
            result["updated_at"] = result["updated_at"].isoformat()

            return JSONResponse(status_code=200, content=snake_to_camel_dict(result))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating wishlist {wishlist_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update wishlist. Please try again.")


@router.delete("/{wishlist_id}")
@limiter.limit("30/hour")
async def delete_wishlist(request: Request, wishlist_id: str):
    """Delete one of the authenticated user's wishlists."""
    uid = extract_firebase_user_uid(request)

    try:
        async with get_pool_from_request(request).acquire() as conn:
            result = await conn.execute(
                "DELETE FROM wishlists WHERE wishlist_id = $1 AND owner_firebase_uid = $2",
                wishlist_id,
                uid,
            )

            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Wishlist not found")

            return JSONResponse(status_code=200, content={"message": "Wishlist deleted successfully"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting wishlist {wishlist_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete wishlist. Please try again.")


@router.get("/matches")
@limiter.limit("60/minute")
async def get_my_matches(request: Request, unseen: bool = False):
    """
    Get matches for the authenticated user's wishlists, newest first.
    Pass ?unseen=true to get only matches not yet marked as seen (for the reveal-moment feed).
    """
    uid = extract_firebase_user_uid(request)

    query = """
        SELECT m.match_id, m.wishlist_id, m.listing_id, m.category, m.matched_at, m.seen_at,
               w.keywords as wishlist_keywords
        FROM wishlist_matches m
        JOIN wishlists w ON w.wishlist_id = m.wishlist_id
        WHERE m.owner_firebase_uid = $1
    """
    params = [uid]

    if unseen:
        query += " AND m.seen_at IS NULL"

    query += " ORDER BY m.matched_at DESC"

    try:
        async with get_pool_from_request(request).acquire() as conn:
            rows = await conn.fetch(query, *params)

            matches_by_category: dict[str, list[str]] = {}
            for row in rows:
                matches_by_category.setdefault(row["category"], []).append(str(row["listing_id"]))

            listing_titles: dict[str, str] = {}
            for category, listing_ids in matches_by_category.items():
                listing_rows = await conn.fetch(
                    f"SELECT listing_id, title FROM {category} WHERE listing_id = ANY($1::uuid[])",
                    listing_ids,
                )
                for listing_row in listing_rows:
                    listing_titles[str(listing_row["listing_id"])] = listing_row["title"]

            matches = []
            for row in rows:
                item = dict(row)
                item["match_id"] = str(item["match_id"])
                item["wishlist_id"] = str(item["wishlist_id"])
                item["listing_id"] = str(item["listing_id"])
                item["listing_title"] = listing_titles.get(item["listing_id"])
                item["matched_at"] = item["matched_at"].isoformat()
                if item.get("seen_at"):
                    item["seen_at"] = item["seen_at"].isoformat()
                matches.append(snake_to_camel_dict(item))

            return JSONResponse(status_code=200, content={"matches": matches})

    except Exception as e:
        logger.error(f"Error fetching wishlist matches for user {uid}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch matches. Please try again.")


@router.post("/matches/{match_id}/seen")
@limiter.limit("60/minute")
async def mark_match_seen(request: Request, match_id: str):
    """Mark a match as seen, once the reveal-moment animation has played."""
    uid = extract_firebase_user_uid(request)

    try:
        async with get_pool_from_request(request).acquire() as conn:
            result = await conn.execute(
                """
                UPDATE wishlist_matches
                SET seen_at = NOW()
                WHERE match_id = $1 AND owner_firebase_uid = $2 AND seen_at IS NULL
                """,
                match_id,
                uid,
            )

            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Match not found or already seen")

            return JSONResponse(status_code=200, content={"message": "Match marked as seen"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking match {match_id} as seen: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update match. Please try again.")
