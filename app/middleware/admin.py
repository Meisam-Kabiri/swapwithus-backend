"""
Admin authentication middleware
Verifies that the authenticated user has admin privileges
"""

from fastapi import HTTPException, Request
from app.middleware.auth import extract_firebase_user_uid
from app.database.connection import get_pool_from_request



async def verify_admin(request: Request) -> str:
    """
    Verify that the authenticated user is an admin

    Args:
        request: FastAPI request object

    Returns:
        str: The admin user's Firebase UID

    Raises:
        HTTPException: If user is not authenticated or not an admin
    """
    # First verify user is authenticated
    uid = extract_firebase_user_uid(request)

    # Check if user has admin privileges in database
    async with get_pool_from_request(request).acquire() as conn:
        result = await conn.fetchrow(
            "SELECT is_admin FROM users WHERE owner_firebase_uid = $1",
            uid
        )

        if not result:
            raise HTTPException(
                status_code=403,
                detail="User not found"
            )

        if not result["is_admin"]:
            raise HTTPException(
                status_code=403,
                detail="Admin privileges required"
            )

    return uid
