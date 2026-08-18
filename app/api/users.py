import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database.connection import get_pool_from_request
from app.database.query_builder import QueryBuilder
from app.middleware.auth import extract_firebase_user_uid, verify_user_owns_resource
from app.middleware.rate_limit import limiter
from app.models.user import UserCreate, UserUpdate
from app.services.gcp_image_service import delete_all_images_from_storage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
@limiter.limit("100/minute")
async def get_my_user_data(
    request: Request,
    uid: str = Depends(extract_firebase_user_uid),
):
    """
    Get current user's own profile data
    UID is extracted from Firebase token, not from URL
    """
    query = """
        SELECT owner_firebase_uid, email, name, profile_image, phone_country_code, phone_number,
               linkedin_url, instagram_id, facebook_id, created_at, updated_at
        FROM users
        WHERE owner_firebase_uid = $1
    """
    async with get_pool_from_request(request).acquire() as conn:
        user_row = await conn.fetchrow(query, uid)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(user_row)


@router.patch("/me")
@limiter.limit("10/minute")
async def update_my_user_data(
    request: Request,
    user: UserUpdate,
    uid: str = Depends(extract_firebase_user_uid),
):
    """
    Update current user's own profile data
    UID is extracted from Firebase token, not from URL
    """
    query = """
        UPDATE users
        SET
            name = $1,
            phone_country_code = $2,
            phone_number = $3,
            linkedin_url = $4,
            instagram_id = $5,
            facebook_id = $6,
            profile_image = $7,
            updated_at = NOW()
        WHERE owner_firebase_uid = $8
    """

    user_dict = user.model_dump(exclude_none=True)
    logger.info(f"Updating user {uid} with fields: {list(user_dict.keys())}")

    try:
        async with get_pool_from_request(request).acquire() as conn:
            result = await conn.execute(
                query,
                user_dict.get("name"),
                user_dict.get("phone_country_code"),
                user_dict.get("phone_number"),
                user_dict.get("linkedin_url"),
                user_dict.get("instagram_id"),
                user_dict.get("facebook_id"),
                user_dict.get("profile_image"),
                uid,
            )
            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="User not found")

            logger.info(f"Successfully updated user: {uid}")
            return JSONResponse(status_code=200, content={"message": "User updated successfully"})

    except Exception as e:
        logger.error(f"Error updating user {uid}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update user. Please try again.")

     
@router.get("/{uid}")
@limiter.limit("100/minute")
async def get_user_data(uid: str, request: Request):
    """
    Get another user's PUBLIC profile data (for viewing their listings)
    Returns limited public information + stats calculated from reviews
    """
    async with get_pool_from_request(request).acquire() as conn:
        # Get basic user info
        user_row = await conn.fetchrow(
            "SELECT owner_firebase_uid, name, profile_image FROM users WHERE owner_firebase_uid = $1",
            uid
        )
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        # Calculate stats dynamically from reviews table
        stats_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)::INTEGER as total_reviews,
                COALESCE(AVG(rating), 0)::DECIMAL(3,2) as average_rating
            FROM reviews
            WHERE reviewee_uid = $1
            """,
            uid
        )

        # Get total swaps completed
        swaps_row = await conn.fetchrow(
            """
            SELECT COUNT(*)::INTEGER as total_swaps
            FROM swaps
            WHERE status = 'completed' AND (user_a_uid = $1 OR user_b_uid = $1)
            """,
            uid
        )

        # Build response with camelCase field names
        total_reviews = stats_row["total_reviews"] if stats_row else 0
        average_rating = float(stats_row["average_rating"]) if stats_row and stats_row["average_rating"] else 0.0
        total_swaps = swaps_row["total_swaps"] if swaps_row else 0
        trust_score = int((average_rating * 10) + total_reviews) if average_rating > 0 else 0

        user_data = {
            "owner_firebase_uid": user_row["owner_firebase_uid"],
            "name": user_row["name"],
            "profileImage": user_row["profile_image"],
            "totalReviews": total_reviews,
            "averageRating": average_rating,
            "totalSwapsCompleted": total_swaps,
            "trustScore": trust_score
        }

        return user_data


@router.get("/{uid}/listings")
@limiter.limit("100/minute")
async def get_user_listings(uid: str, request: Request):
    """
    Get all public listings for a specific user
    Returns listings from all categories (homes, books, clothes, caravans)
    """
    try:
        async with get_pool_from_request(request).acquire() as conn:
            # Get listings from all category tables
            all_listings = []

            # Homes
            homes_query = """
                SELECT listing_id, 'homes' as category, title, city, country, created_at,
                       (SELECT cdn_url FROM images WHERE listing_id = h.listing_id AND is_hero = TRUE LIMIT 1) as hero_image_url
                FROM homes h
                WHERE owner_firebase_uid = $1
                ORDER BY created_at DESC
            """
            homes_rows = await conn.fetch(homes_query, uid)
            for row in homes_rows:
                listing_dict = dict(row)
                listing_dict["listingId"] = str(listing_dict.pop("listing_id"))
                all_listings.append(listing_dict)

            # Books
            books_query = """
                SELECT listing_id, 'books' as category, title, city, country, created_at,
                       (SELECT cdn_url FROM images WHERE listing_id = b.listing_id AND is_hero = TRUE LIMIT 1) as hero_image_url
                FROM books b
                WHERE owner_firebase_uid = $1
                ORDER BY created_at DESC
            """
            books_rows = await conn.fetch(books_query, uid)
            for row in books_rows:
                listing_dict = dict(row)
                listing_dict["listingId"] = str(listing_dict.pop("listing_id"))
                all_listings.append(listing_dict)

            # Clothes
            clothes_query = """
                SELECT listing_id, 'clothes' as category, title, city, country, created_at,
                       (SELECT cdn_url FROM images WHERE listing_id = c.listing_id AND is_hero = TRUE LIMIT 1) as hero_image_url
                FROM clothes c
                WHERE owner_firebase_uid = $1
                ORDER BY created_at DESC
            """
            clothes_rows = await conn.fetch(clothes_query, uid)
            for row in clothes_rows:
                listing_dict = dict(row)
                listing_dict["listingId"] = str(listing_dict.pop("listing_id"))
                all_listings.append(listing_dict)

            # Caravans
            caravans_query = """
                SELECT listing_id, 'caravans' as category, title, city, country, created_at,
                       (SELECT cdn_url FROM images WHERE listing_id = cv.listing_id AND is_hero = TRUE LIMIT 1) as hero_image_url
                FROM caravans cv
                WHERE owner_firebase_uid = $1
                ORDER BY created_at DESC
            """
            caravans_rows = await conn.fetch(caravans_query, uid)
            for row in caravans_rows:
                listing_dict = dict(row)
                listing_dict["listingId"] = str(listing_dict.pop("listing_id"))
                all_listings.append(listing_dict)

            # Sort all listings by created_at desc
            all_listings.sort(key=lambda x: x["created_at"], reverse=True)

            # Convert datetime to ISO string
            for listing in all_listings:
                if listing.get("created_at"):
                    listing["created_at"] = listing["created_at"].isoformat()

            return JSONResponse(status_code=200, content={"listings": all_listings})

    except Exception as e:
        logger.error(f"Error fetching listings for user {uid}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch user listings. Please try again.")


@router.post("")
@limiter.limit("5/hour")
async def create_user(
    request: Request,
    user: UserCreate,
    user_uid: str = Depends(extract_firebase_user_uid),
):
    """
    Create a new user account.

    Called after Firebase signup (email/password, Google, or Facebook).
    Verifies Firebase token and creates user record in database.
    """
    # Verify the token UID matches the user being created
    if user.owner_firebase_uid != user_uid:
        raise HTTPException(403, "Cannot create user account for another user")

    try:
        user_dict = user.model_dump()

        # Build insert query
        insert_query, insert_values = QueryBuilder.build_insert_query(user_dict, "users")

        # Execute with pool
        async with get_pool_from_request(request).acquire() as conn:
            await conn.execute(insert_query, *insert_values)

        logger.info("New user UID from DB: %s", user_dict.get("owner_firebase_uid"))
        return JSONResponse(
            status_code=201,
            content={
                "uid": user_dict.get("owner_firebase_uid"),
                "message": "User created successfully",
            },
        )
    except Exception as e:
        logger.error(f"Error creating user: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create user. Please try again.")


# DELETE /{uid} (Delete Account)
@router.delete("/{uid}")
@limiter.limit("3/hour")
async def delete_user(request: Request, uid: str):
    # Verify user can only delete their own account
    verify_user_owns_resource(request, uid)

    try:
        async with get_pool_from_request(request).acquire() as conn:
            # First delete user's listings (if any)
            exist_user = await conn.fetchval(
                "SELECT 1 FROM users WHERE owner_firebase_uid = $1", uid
            )
            if not exist_user:
                logger.info(f"User {uid} not in database, skipping deletion")
                return JSONResponse(
                    status_code=200,
                    content={"message": "User not in database but deleted successfully"},
                )

            async with conn.transaction():
                # Get all images to delete from storage (simpler query)
                image_urls = await conn.fetch(
                    "SELECT public_url FROM images WHERE owner_firebase_uid = $1", uid
                )

                # Delete user (CASCADE will delete homes and images from DB)
                result = await conn.execute("DELETE FROM users WHERE owner_firebase_uid = $1", uid)
                if result == "DELETE 0":
                    raise HTTPException(status_code=404, detail="User not found")

            # Delete images from storage after DB transaction
            await delete_all_images_from_storage([image["public_url"] for image in image_urls])

            logger.info(f"Successfully deleted user and images for userID: {uid}")
            return JSONResponse(
                status_code=200, content={"message": "User and related data deleted successfully"}
            )

    except Exception as e:
        logger.error(f"Error deleting user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete user. Please try again.")


@router.patch("/{uid}")
@limiter.limit("10/minute")
async def update_user(request: Request, uid: str, user: UserUpdate):

    # Verify user can only update their own account
    verify_user_owns_resource(request, uid)
    query = """   UPDATE users
                SET
                name = $1,
                phone_country_code = $2,
                phone_number = $3,
                linkedin_url = $4,
                instagram_id = $5,
                facebook_id = $6,
                profile_image = $7,
                updated_at = NOW()
                WHERE owner_firebase_uid = $8 """
    user_dict = user.model_dump(exclude_none=True)
    logger.info(f"Updating user {uid} with fields: {list(user_dict.keys())}")
    try:
        async with get_pool_from_request(request).acquire() as conn:
            result = await conn.execute(
                query,
                user_dict.get("name"),
                user_dict.get("phone_country_code"),
                user_dict.get("phone_number"),
                user_dict.get("linkedin_url"),
                user_dict.get("instagram_id"),
                user_dict.get("facebook_id"),
                user_dict.get("profile_image"),
                uid,
            )
            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="User not found")
            logger.info(f"Successfully updated user: {uid}")
            return JSONResponse(status_code=200, content={"message": "User updated successfully"})
    except Exception as e:
        logger.error(f"Error updating user {uid}: {type(e).__name__}: {str(e)}", exc_info=True)
