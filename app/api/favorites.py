from fastapi import APIRouter, Request, HTTPException
from app.middleware.auth import extract_firebase_user_uid
from app.database.connection import get_pool
from app.middleware.rate_limit import limiter
from app.utils.cdn_auth import make_urlprefix_token, append_token_to_url
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/favorites", tags=["favorites"])

@router.delete("/{listing_id}")
@limiter.limit("50/minute")
async def remove_favorite(request: Request, listing_id: str):
    user_id = extract_firebase_user_uid(request)
    logger.info(f"Removing favorite for listing {listing_id}, user {user_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not listing_id:
        raise HTTPException(status_code=400, detail="listing_id is required")

    remove_favorite_query = """
  DELETE FROM favorites
  WHERE owner_firebase_uid = $1 AND listing_id = $2
  """
    async with get_pool().acquire() as conn:
        try:
            await conn.execute(remove_favorite_query, user_id, listing_id)
            return {"message": "Listing removed from favorites"}
        except Exception as e:
            logger.error(f"Error removing favorite: {e}")
            raise HTTPException(status_code=500, detail="Failed to remove favorite")


@router.post("")
@limiter.limit("50/minute")
async def add_favorite(request: Request):
    user_id = extract_firebase_user_uid(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    listing_id = body.get("listing_id")
    logger.info(f"Adding favorite for listing {listing_id}, user {user_id}")
    if not listing_id:
        raise HTTPException(status_code=400, detail="listing_id is required")

    add_favorite_query = """
  INSERT INTO favorites (owner_firebase_uid, listing_id, created_at)
  Values ($1, $2, NOW())
  ON CONFLICT (owner_firebase_uid, listing_id) DO NOTHING
  """
    async with get_pool().acquire() as conn:
        try:
            await conn.execute(add_favorite_query, user_id, listing_id)
            return {"message": "Listing added to favorites"}
        except Exception as e:
            logger.error(f"Error adding favorite: {e}")
            raise HTTPException(status_code=500, detail="Failed to add favorite")


@router.get("")
@limiter.limit("50/minute")
async def get_favorites(request: Request):
    user_id = extract_firebase_user_uid(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    get_favorites_query = """
    SELECT h.*,
    f.listing_id,
    i.public_url as hero_image_url
    FROM homes h
    Join favorites f ON h.listing_id = f.listing_id
    LEFT JOIN images i ON h.listing_id = i.listing_id AND i.is_hero = TRUE
    WHERE f.owner_firebase_uid = $1
    """
    async with get_pool().acquire() as conn:
        try:
            favorite_rows = await conn.fetch(get_favorites_query, user_id)
            favorites = [dict(row) for row in favorite_rows]
            for favorite in favorites:
                if favorite.get("hero_image_url"):
                    favorite["signed_url"] = append_token_to_url(
                        favorite["hero_image_url"],
                        make_urlprefix_token("https://cdn.swapwithus.com/home/"),
                    )
            return favorites
        except Exception as e:
            logger.error(f"Error fetching favorites: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch favorites")