import os

import firebase_admin  # type: ignore
from fastapi import HTTPException, Request
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

# Initialize Firebase Admin (only once)
if not firebase_admin._apps:
    # Try absolute path first (Docker), then relative path (local)
    import os

    if os.path.exists("/app/swapwithus-project-firebase-adminsdk.json"):
        cred = credentials.Certificate("/app/swapwithus-project-firebase-adminsdk.json")
    else:
        cred = credentials.Certificate("./swapwithus-project-firebase-adminsdk.json")
    firebase_admin.initialize_app(cred)


def extract_firebase_user_uid(request: Request) -> str:
    """
    Verify Firebase token and return the user UID
    Raises HTTPException if token is invalid or missing
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.split("Bearer ")[1]

    try:
        decoded_token = firebase_auth.verify_id_token(token)
        return decoded_token["uid"]
    except Exception:
        # Don't expose Firebase error details to user
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def verify_user_owns_resource(request: Request, claimed_uid: str):
    """
    Verify that the authenticated user matches the claimed UID
    """
    actual_uid = extract_firebase_user_uid(request)

    if actual_uid != claimed_uid:
        raise HTTPException(
            status_code=403, detail="You don't have permission to access this resource"
        )

    return actual_uid
