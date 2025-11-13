
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import logging
from app.database.connection import get_pool
from app.database.query_builder import QueryBuilder
from app.models.user import UserCreate, UserUpdate
from app.middleware.auth import verify_firebase_token, verify_user_owns_resource
from app.services.gcp_image_service import delete_image_from_storage
from app.middleware.rate_limit import  limiter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


router  = APIRouter(prefix="/users", tags=["users"])
@router.get("me")
@limiter.limit("100/minute")
async def get_my_user_data(request: Request):
    """
    Get current user's own profile data
    UID is extracted from Firebase token, not from URL
    """
    # Extract UID from token
    uid = verify_firebase_token(request)

    query = """
        SELECT owner_firebase_uid, email, name, profile_image, phone_country_code, phone_number,
               linkedin_url, instagram_id, facebook_id, created_at, updated_at
        FROM users
        WHERE owner_firebase_uid = $1
    """
    async with get_pool().acquire() as conn:
        user_row = await conn.fetchrow(query, uid)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(user_row)


@router.get("/{uid}")
@limiter.limit("100/minute")
async def get_user_data(uid: str, request: Request):
    """
    Get another user's PUBLIC profile data (for viewing their listings)
    Returns limited public information only - no authentication required
    """
    query = """
        SELECT owner_firebase_uid, name, profile_image
        FROM users
        WHERE owner_firebase_uid = $1
    """
    async with get_pool().acquire() as conn:
        user_row = await conn.fetchrow(query, uid)
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(user_row)


@router.post("")
@limiter.limit("5/hour")
async def create_user(request: Request, user: UserCreate):
    """
    Create a new user account.

    Called after Firebase signup (email/password, Google, or Facebook).
    Verifies Firebase token and creates user record in database.
    """
    # Verify Firebase token
    user_uid = verify_firebase_token(request)

    # Verify the token UID matches the user being created
    if user.owner_firebase_uid != user_uid:
        raise HTTPException(403, "Cannot create user account for another user")

    try:
        user_dict = user.model_dump()

        # Build insert query
        insert_query, insert_values = QueryBuilder.build_insert_query(user_dict, "users")

        # Execute with pool
        async with get_pool().acquire() as conn:
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
        async with get_pool().acquire() as conn:
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
            for image in image_urls:
                await delete_image_from_storage(image["public_url"])

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
        async with get_pool().acquire() as conn:
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

