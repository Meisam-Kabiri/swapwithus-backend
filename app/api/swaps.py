import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database.connection import get_pool
from app.middleware.auth import extract_firebase_user_uid
from app.middleware.rate_limit import limiter
from app.models.swap import SwapCreate, SwapUpdate

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


router = APIRouter(prefix="/swaps", tags=["swaps"])


def snake_to_camel_dict(data):
    """Convert snake_case keys to camelCase in dict"""
    if not isinstance(data, dict):
        return data

    result = {}
    for key, value in data.items():
        # Convert snake_case to camelCase
        parts = key.split('_')
        camel_key = parts[0] + ''.join(word.capitalize() for word in parts[1:])
        result[camel_key] = value
    return result


@router.post("")
@limiter.limit("20/hour")
async def create_swap(request: Request, swap: SwapCreate):
    """
    Create a new swap request.
    User A initiates swap with User B.
    """
    user_a_uid = extract_firebase_user_uid(request)

    # Verify user is not swapping with themselves
    if user_a_uid == swap.user_b_uid:
        raise HTTPException(status_code=400, detail="Cannot create swap with yourself")

    swap_dict = swap.model_dump()
    swap_dict["user_a_uid"] = user_a_uid
    swap_dict["status"] = "pending"

    query = """
        INSERT INTO swaps (user_a_uid, user_b_uid, listing_a_id, listing_b_id, conversation_id, status, initiated_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        RETURNING swap_id, created_at, updated_at, user_a_uid, user_b_uid, listing_a_id, listing_b_id,
                  status, conversation_id, user_a_confirmed, user_b_confirmed, initiated_at
    """

    try:
        async with get_pool().acquire() as conn:
            # Check for existing active swap between these users with same listings
            existing_swap = await conn.fetchrow(
                """
                SELECT swap_id, status FROM swaps
                WHERE ((user_a_uid = $1 AND user_b_uid = $2) OR (user_a_uid = $2 AND user_b_uid = $1))
                AND ((listing_a_id = $3 AND listing_b_id = $4) OR (listing_a_id = $4 AND listing_b_id = $3))
                AND status IN ('pending', 'accepted')
                """,
                user_a_uid,
                swap_dict["user_b_uid"],
                swap_dict["listing_a_id"],
                swap_dict["listing_b_id"],
            )

            if existing_swap:
                status = existing_swap['status']
                logger.warning(f"Duplicate swap attempt blocked: existing swap with status '{status}'")
                raise HTTPException(
                    status_code=400,
                    detail=f"An active swap request already exists (status: {status}). Please check your swaps page."
                )

            swap_row = await conn.fetchrow(
                query,
                user_a_uid,
                swap_dict["user_b_uid"],
                swap_dict["listing_a_id"],
                swap_dict["listing_b_id"],
                swap_dict.get("conversation_id"),
                "pending",
            )

            if not swap_row:
                raise HTTPException(status_code=500, detail="Failed to create swap")

            result = dict(swap_row)
            # Convert UUID to string
            result["swap_id"] = str(result["swap_id"])
            result["listing_a_id"] = str(result["listing_a_id"])
            result["listing_b_id"] = str(result["listing_b_id"])
            # Convert datetime to ISO string
            result["created_at"] = result["created_at"].isoformat()
            result["updated_at"] = result["updated_at"].isoformat()
            result["initiated_at"] = result["initiated_at"].isoformat()

            logger.info(f"Created swap {result['swap_id']} between {user_a_uid} and {swap_dict['user_b_uid']}")
            return JSONResponse(status_code=201, content=snake_to_camel_dict(result))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating swap: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create swap. Please try again.")


@router.get("")
@limiter.limit("100/minute")
async def get_my_swaps(request: Request, status: str | None = None):
    """
    Get all swaps for the current user (both as user_a and user_b).
    Optionally filter by status.
    """
    uid = extract_firebase_user_uid(request)

    query = """
        SELECT s.swap_id, s.created_at, s.updated_at, s.user_a_uid, s.user_b_uid,
               s.listing_a_id, s.listing_b_id, s.status, s.conversation_id,
               s.user_a_confirmed, s.user_b_confirmed, s.completed_at,
               s.initiated_at, s.accepted_at, s.cancelled_at, s.cancelled_by, s.cancellation_reason,
               CASE
                   WHEN s.user_a_uid = $1 THEN u_b.name
                   ELSE u_a.name
               END as other_user_name
        FROM swaps s
        LEFT JOIN users u_a ON s.user_a_uid = u_a.owner_firebase_uid
        LEFT JOIN users u_b ON s.user_b_uid = u_b.owner_firebase_uid
        WHERE s.user_a_uid = $1 OR s.user_b_uid = $1
    """

    params = [uid]

    if status:
        query += " AND s.status = $2"
        params.append(status)

    query += " ORDER BY s.created_at DESC"

    try:
        async with get_pool().acquire() as conn:
            rows = await conn.fetch(query, *params)

            swaps = []
            for row in rows:
                swap_dict = dict(row)
                # Convert UUID to string
                swap_dict["swap_id"] = str(swap_dict["swap_id"])
                swap_dict["listing_a_id"] = str(swap_dict["listing_a_id"])
                swap_dict["listing_b_id"] = str(swap_dict["listing_b_id"])
                # Convert datetime fields to ISO strings
                for field in ["created_at", "updated_at", "initiated_at", "accepted_at", "cancelled_at", "completed_at"]:
                    if swap_dict.get(field):
                        swap_dict[field] = swap_dict[field].isoformat()

                swaps.append(snake_to_camel_dict(swap_dict))

            return JSONResponse(status_code=200, content={"swaps": swaps})

    except Exception as e:
        logger.error(f"Error fetching swaps for user {uid}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch swaps. Please try again.")


@router.get("/{swap_id}")
@limiter.limit("100/minute")
async def get_swap(request: Request, swap_id: str):
    """
    Get details of a specific swap.
    User must be participant in the swap.
    """
    uid = extract_firebase_user_uid(request)

    query = """
        SELECT swap_id, created_at, updated_at, user_a_uid, user_b_uid,
               listing_a_id, listing_b_id, status, conversation_id,
               user_a_confirmed, user_b_confirmed, completed_at,
               initiated_at, accepted_at, cancelled_at, cancelled_by, cancellation_reason
        FROM swaps
        WHERE swap_id = $1
    """

    try:
        async with get_pool().acquire() as conn:
            swap_row = await conn.fetchrow(query, swap_id)

            if not swap_row:
                raise HTTPException(status_code=404, detail="Swap not found")

            swap_dict = dict(swap_row)

            # Verify user is participant
            if swap_dict["user_a_uid"] != uid and swap_dict["user_b_uid"] != uid:
                raise HTTPException(status_code=403, detail="Not authorized to view this swap")

            # Convert UUID to string
            swap_dict["swap_id"] = str(swap_dict["swap_id"])
            swap_dict["listing_a_id"] = str(swap_dict["listing_a_id"])
            swap_dict["listing_b_id"] = str(swap_dict["listing_b_id"])
            # Convert datetime fields to ISO strings
            for field in ["created_at", "updated_at", "initiated_at", "accepted_at", "cancelled_at", "completed_at"]:
                if swap_dict.get(field):
                    swap_dict[field] = swap_dict[field].isoformat()

            return JSONResponse(status_code=200, content=snake_to_camel_dict(swap_dict))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching swap {swap_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch swap. Please try again.")


@router.patch("/{swap_id}/accept")
@limiter.limit("20/hour")
async def accept_swap(request: Request, swap_id: str):
    """
    Accept a swap request.
    Only user_b can accept.
    """
    uid = extract_firebase_user_uid(request)

    try:
        async with get_pool().acquire() as conn:
            # Get current swap
            swap_row = await conn.fetchrow("SELECT user_a_uid, user_b_uid, status FROM swaps WHERE swap_id = $1", swap_id)

            if not swap_row:
                raise HTTPException(status_code=404, detail="Swap not found")

            # Verify user is user_b
            if swap_row["user_b_uid"] != uid:
                raise HTTPException(status_code=403, detail="Only the recipient can accept the swap")

            # Verify status is pending
            if swap_row["status"] != "pending":
                raise HTTPException(status_code=400, detail="Swap is not pending")

            # Update to accepted
            result = await conn.execute(
                """
                UPDATE swaps
                SET status = 'accepted', accepted_at = NOW(), updated_at = NOW()
                WHERE swap_id = $1
                """,
                swap_id,
            )

            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Swap not found")

            logger.info(f"User {uid} accepted swap {swap_id}")
            return JSONResponse(status_code=200, content={"message": "Swap accepted successfully"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting swap {swap_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to accept swap. Please try again.")


@router.patch("/{swap_id}/decline")
@limiter.limit("20/hour")
async def decline_swap(request: Request, swap_id: str, swap_update: SwapUpdate):
    """
    Decline a swap request.
    Only user_b can decline.
    """
    uid = extract_firebase_user_uid(request)

    try:
        async with get_pool().acquire() as conn:
            # Get current swap
            swap_row = await conn.fetchrow("SELECT user_a_uid, user_b_uid, status FROM swaps WHERE swap_id = $1", swap_id)

            if not swap_row:
                raise HTTPException(status_code=404, detail="Swap not found")

            # Verify user is user_b
            if swap_row["user_b_uid"] != uid:
                raise HTTPException(status_code=403, detail="Only the recipient can decline the swap")

            # Verify status is pending
            if swap_row["status"] != "pending":
                raise HTTPException(status_code=400, detail="Swap is not pending")

            # Update to cancelled
            result = await conn.execute(
                """
                UPDATE swaps
                SET status = 'cancelled', cancelled_at = NOW(), cancelled_by = $1,
                    cancellation_reason = $2, updated_at = NOW()
                WHERE swap_id = $3
                """,
                uid,
                swap_update.cancellation_reason,
                swap_id,
            )

            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Swap not found")

            logger.info(f"User {uid} declined swap {swap_id}")
            return JSONResponse(status_code=200, content={"message": "Swap declined successfully"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error declining swap {swap_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to decline swap. Please try again.")


@router.post("/{swap_id}/confirm-receipt")
@limiter.limit("20/hour")
async def confirm_receipt(request: Request, swap_id: str):
    """
    Confirm receipt of swapped item.
    When both users confirm, swap status changes to 'completed'.
    """
    uid = extract_firebase_user_uid(request)

    try:
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                # Get current swap
                swap_row = await conn.fetchrow(
                    "SELECT user_a_uid, user_b_uid, status, user_a_confirmed, user_b_confirmed FROM swaps WHERE swap_id = $1 FOR UPDATE",
                    swap_id,
                )

                if not swap_row:
                    raise HTTPException(status_code=404, detail="Swap not found")

                # Verify user is participant
                if swap_row["user_a_uid"] != uid and swap_row["user_b_uid"] != uid:
                    raise HTTPException(status_code=403, detail="Not authorized to confirm this swap")

                # Verify status is accepted
                if swap_row["status"] != "accepted":
                    raise HTTPException(status_code=400, detail="Swap must be accepted before confirming receipt")

                # Determine which user is confirming
                is_user_a = swap_row["user_a_uid"] == uid
                user_a_confirmed = swap_row["user_a_confirmed"]
                user_b_confirmed = swap_row["user_b_confirmed"]

                # Check if already confirmed
                if (is_user_a and user_a_confirmed) or (not is_user_a and user_b_confirmed):
                    raise HTTPException(status_code=400, detail="You have already confirmed receipt")

                # Update confirmation
                if is_user_a:
                    user_a_confirmed = True
                else:
                    user_b_confirmed = True

                # Check if both confirmed
                both_confirmed = user_a_confirmed and user_b_confirmed

                if both_confirmed:
                    # Mark as completed
                    await conn.execute(
                        """
                        UPDATE swaps
                        SET user_a_confirmed = $1, user_b_confirmed = $2,
                            status = 'completed', completed_at = NOW(), updated_at = NOW()
                        WHERE swap_id = $3
                        """,
                        user_a_confirmed,
                        user_b_confirmed,
                        swap_id,
                    )

                    # Update user stats
                    await conn.execute(
                        """
                        UPDATE users
                        SET total_swaps_completed = total_swaps_completed + 1,
                            last_swap_at = NOW()
                        WHERE owner_firebase_uid = $1 OR owner_firebase_uid = $2
                        """,
                        swap_row["user_a_uid"],
                        swap_row["user_b_uid"],
                    )

                    logger.info(f"Swap {swap_id} completed by both users")
                    return JSONResponse(
                        status_code=200, content={"message": "Swap completed! Both parties confirmed receipt."}
                    )
                else:
                    # Just update confirmation
                    await conn.execute(
                        """
                        UPDATE swaps
                        SET user_a_confirmed = $1, user_b_confirmed = $2, updated_at = NOW()
                        WHERE swap_id = $3
                        """,
                        user_a_confirmed,
                        user_b_confirmed,
                        swap_id,
                    )

                    logger.info(f"User {uid} confirmed receipt for swap {swap_id}")
                    return JSONResponse(
                        status_code=200, content={"message": "Receipt confirmed. Waiting for other party to confirm."}
                    )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming receipt for swap {swap_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to confirm receipt. Please try again.")


@router.patch("/{swap_id}/cancel")
@limiter.limit("20/hour")
async def cancel_swap(request: Request, swap_id: str, swap_update: SwapUpdate):
    """
    Cancel a swap.
    Either party can cancel before completion.
    """
    uid = extract_firebase_user_uid(request)

    try:
        async with get_pool().acquire() as conn:
            # Get current swap
            swap_row = await conn.fetchrow(
                "SELECT user_a_uid, user_b_uid, status FROM swaps WHERE swap_id = $1", swap_id
            )

            if not swap_row:
                raise HTTPException(status_code=404, detail="Swap not found")

            # Verify user is participant
            if swap_row["user_a_uid"] != uid and swap_row["user_b_uid"] != uid:
                raise HTTPException(status_code=403, detail="Not authorized to cancel this swap")

            # Verify status is not already completed or cancelled
            if swap_row["status"] == "completed":
                raise HTTPException(status_code=400, detail="Cannot cancel completed swap")

            if swap_row["status"] == "cancelled":
                raise HTTPException(status_code=400, detail="Swap is already cancelled")

            # Update to cancelled
            result = await conn.execute(
                """
                UPDATE swaps
                SET status = 'cancelled', cancelled_at = NOW(), cancelled_by = $1,
                    cancellation_reason = $2, updated_at = NOW()
                WHERE swap_id = $3
                """,
                uid,
                swap_update.cancellation_reason,
                swap_id,
            )

            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Swap not found")

            logger.info(f"User {uid} cancelled swap {swap_id}")
            return JSONResponse(status_code=200, content={"message": "Swap cancelled successfully"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling swap {swap_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to cancel swap. Please try again.")
