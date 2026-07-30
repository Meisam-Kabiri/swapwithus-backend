"""
Swap API - unified on the chain engine (swap_chains + swap_legs).

A direct 2-person swap is just a chain with 2 legs, so every endpoint here drives
the same engine in app/services/swap_chain_service.py:

  - POST /swaps                     direct request: I offer my listing for yours
                                    (creates a 2-leg chain; my leg is pre-accepted)
  - GET  /swaps                     my chains (optionally ?status=)
  - GET  /swaps/{chain_id}          one chain's detail
  - POST /swaps/{chain_id}/accept   a giver accepts their leg
  - POST /swaps/{chain_id}/decline  cancel/decline (any participant)
  - POST /swaps/{chain_id}/confirm-receipt   a receiver confirms they got the item
  - POST /swaps/{chain_id}/cancel   cancel (any participant)

System-discovered multi-way chains (from wishlist cycle detection) reuse the same
service + the same accept/confirm/cancel endpoints; only their creation differs.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database.connection import get_pool_from_request
from app.middleware.auth import extract_firebase_user_uid
from app.middleware.rate_limit import limiter
from app.models.swap import ChainProposeRequest, SwapCreate
from app.services import swap_chain_service as svc
from app.services.swap_chain_finder import SwapEdge

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/swaps", tags=["swaps"])


def _raise_http(e: Exception) -> None:
    """Map service-layer errors to HTTP responses."""
    if isinstance(e, PermissionError):
        raise HTTPException(status_code=403, detail=str(e))
    if isinstance(e, LookupError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=400, detail=str(e))
    raise e


@router.post("")
@limiter.limit("20/hour")
async def create_swap(
    request: Request,
    swap: SwapCreate,
    my_uid: str = Depends(extract_firebase_user_uid),
):
    """
    Direct request: I offer my own listing in exchange for the one I want. The
    other party (their_listing's owner) is resolved server-side - the client never
    sends it. Creates a 2-leg chain; my leg is pre-accepted, they must accept.
    """
    try:
        async with get_pool_from_request(request).acquire() as conn:
            # Resolve both owners from the listings themselves.
            my_listing_owner = await svc.get_listing_owner(
                conn, swap.my_listing_category, swap.my_listing_id
            )
            their_listing_owner = await svc.get_listing_owner(
                conn, swap.their_listing_category, swap.their_listing_id
            )
            if my_listing_owner is None:
                raise HTTPException(status_code=404, detail="Your listing was not found")
            if their_listing_owner is None:
                raise HTTPException(status_code=404, detail="The requested listing was not found")
            # You can only offer YOUR item.
            if my_listing_owner != my_uid:
                raise HTTPException(status_code=403, detail="You can only offer your own listing")
            # The other party is whoever owns the listing I want; not myself.
            their_uid = their_listing_owner
            if their_uid == my_uid:
                raise HTTPException(status_code=400, detail="Cannot create swap with yourself")

            legs = [
                # I give my listing to them (pre-accepted below)
                SwapEdge(my_uid, their_uid, swap.my_listing_id, swap.my_listing_category),
                # they give their listing to me (they must still accept)
                SwapEdge(their_uid, my_uid, swap.their_listing_id, swap.their_listing_category),
            ]
            chain = await svc.propose_chain(
                conn, legs, conversation_id=swap.conversation_id, auto_accept_from_user=my_uid
            )
            return JSONResponse(status_code=201, content=chain)

    except HTTPException:
        raise
    except (ValueError, PermissionError, LookupError) as e:
        _raise_http(e)
    except Exception as e:
        logger.error(f"Error creating swap: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create swap. Please try again.")


@router.get("")
@limiter.limit("100/minute")
async def get_my_swaps(
    request: Request,
    status: str | None = None,
    uid: str = Depends(extract_firebase_user_uid),
):
    """All swaps the user participates in, newest first. Optional ?status= filter."""
    try:
        async with get_pool_from_request(request).acquire() as conn:
            chains = await svc.get_user_chains(conn, uid, status=status)
            return JSONResponse(status_code=200, content={"swaps": chains})
    except Exception as e:
        logger.error(f"Error fetching swaps for {uid}: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch swaps. Please try again.")


@router.get("/suggestions")
@limiter.limit("60/minute")
async def get_swap_suggestions(
    request: Request,
    uid: str = Depends(extract_firebase_user_uid),
):
    """
    System-discovered swap suggestions for the user (2- and 3-way loops found in
    wishlist matches). Read-only - nothing is created until the user proposes one.
    Defined before /{chain_id} so 'suggestions' isn't read as a chain id.
    """
    try:
        async with get_pool_from_request(request).acquire() as conn:
            suggestions = await svc.find_suggested_chains(conn, uid)
            return JSONResponse(status_code=200, content={"suggestions": suggestions})
    except Exception as e:
        logger.error(f"Error finding suggestions for {uid}: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to find swap suggestions. Please try again.")


@router.post("/suggestions/propose")
@limiter.limit("20/hour")
async def propose_suggested_swap(
    request: Request,
    body: ChainProposeRequest,
    uid: str = Depends(extract_firebase_user_uid),
):
    """Materialise a suggested chain into a real pending swap (your leg pre-accepted)."""
    legs = [
        SwapEdge(leg.from_user, leg.to_user, leg.listing_id, leg.category) for leg in body.legs
    ]
    try:
        async with get_pool_from_request(request).acquire() as conn:
            chain = await svc.propose_suggested_chain(conn, uid, legs)
            return JSONResponse(status_code=201, content=chain)
    except (ValueError, PermissionError, LookupError) as e:
        _raise_http(e)
    except Exception as e:
        logger.error(f"Error proposing suggested swap: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to propose swap. Please try again.")


@router.get("/{chain_id}")
@limiter.limit("100/minute")
async def get_swap(
    request: Request,
    chain_id: str,
    uid: str = Depends(extract_firebase_user_uid),
):
    """One swap's detail (participants only)."""
    try:
        async with get_pool_from_request(request).acquire() as conn:
            chain = await svc.get_chain(conn, chain_id, uid)
            return JSONResponse(status_code=200, content=chain)
    except (ValueError, PermissionError, LookupError) as e:
        _raise_http(e)
    except Exception as e:
        logger.error(f"Error fetching swap {chain_id}: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch swap. Please try again.")


@router.post("/{chain_id}/accept")
@router.patch("/{chain_id}/accept")
@limiter.limit("60/minute")
async def accept_swap(
    request: Request,
    chain_id: str,
    uid: str = Depends(extract_firebase_user_uid),
):
    """A giver accepts their leg. When everyone has accepted, the swap is on."""
    try:
        async with get_pool_from_request(request).acquire() as conn:
            chain = await svc.accept_chain(conn, chain_id, uid)
            return JSONResponse(status_code=200, content=chain)
    except (ValueError, PermissionError, LookupError) as e:
        _raise_http(e)
    except Exception as e:
        logger.error(f"Error accepting swap {chain_id}: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to accept swap. Please try again.")


@router.post("/{chain_id}/decline")
@router.patch("/{chain_id}/decline")
@limiter.limit("60/minute")
async def decline_swap(
    request: Request,
    chain_id: str,
    uid: str = Depends(extract_firebase_user_uid),
):
    """Decline a swap (any participant) - same effect as cancel before completion."""
    try:
        async with get_pool_from_request(request).acquire() as conn:
            chain = await svc.cancel_chain(conn, chain_id, uid)
            return JSONResponse(status_code=200, content=chain)
    except (ValueError, PermissionError, LookupError) as e:
        _raise_http(e)
    except Exception as e:
        logger.error(f"Error declining swap {chain_id}: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to decline swap. Please try again.")


@router.post("/{chain_id}/confirm-receipt")
@limiter.limit("60/minute")
async def confirm_receipt(
    request: Request,
    chain_id: str,
    uid: str = Depends(extract_firebase_user_uid),
):
    """A receiver confirms they got their item. Last confirmation completes the swap."""
    try:
        async with get_pool_from_request(request).acquire() as conn:
            chain = await svc.confirm_receipt(conn, chain_id, uid)
            return JSONResponse(status_code=200, content=chain)
    except (ValueError, PermissionError, LookupError) as e:
        _raise_http(e)
    except Exception as e:
        logger.error(f"Error confirming receipt {chain_id}: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to confirm receipt. Please try again.")


@router.post("/{chain_id}/cancel")
@router.patch("/{chain_id}/cancel")
@limiter.limit("60/minute")
async def cancel_swap(
    request: Request,
    chain_id: str,
    uid: str = Depends(extract_firebase_user_uid),
):
    """Cancel a swap that hasn't completed yet (any participant)."""
    try:
        async with get_pool_from_request(request).acquire() as conn:
            chain = await svc.cancel_chain(conn, chain_id, uid)
            return JSONResponse(status_code=200, content=chain)
    except (ValueError, PermissionError, LookupError) as e:
        _raise_http(e)
    except Exception as e:
        logger.error(f"Error cancelling swap {chain_id}: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to cancel swap. Please try again.")
