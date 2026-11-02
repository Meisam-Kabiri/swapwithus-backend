import os
from dataclasses import dataclass

import firebase_admin  # type: ignore
from fastapi import HTTPException, Request
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

# Initialize Firebase Admin (only once)
if not firebase_admin._apps:
    # Try mounted secret (Cloud Run), then local file
    if os.path.exists("/secrets/firebase-credentials.json"):
        # Cloud Run: Secret Manager mounted as file
        cred = credentials.Certificate("/secrets/firebase-credentials.json")
    else:
        # Local development
        cred = credentials.Certificate("./swapwithus-project-firebase-adminsdk.json")
    firebase_admin.initialize_app(cred)


@dataclass(frozen=True)
class FirebaseUser:
    uid: str
    email: str | None  # Some logins, such as a phone-only Facebook account, have no email
    email_verified: bool


def _decode_firebase_token(request: Request) -> dict:
    """
    Verify the Firebase token and return its contents
    Raises HTTPException if token is invalid or missing
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.split("Bearer ")[1]

    try:
        return firebase_auth.verify_id_token(token)
    except Exception:
        # Don't expose Firebase error details to user
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def extract_firebase_user_uid(request: Request) -> str:
    """Return the UID of the logged-in user."""
    return _decode_firebase_token(request)["uid"]


def get_firebase_user(request: Request) -> FirebaseUser:
    """Return the logged-in user's identity as verified by Firebase, for when more than the UID is needed."""
    decoded_token = _decode_firebase_token(request)
    return FirebaseUser(
        uid=decoded_token["uid"],
        email=decoded_token.get("email"),
        email_verified=decoded_token.get("email_verified", False),
    )


def get_optional_firebase_uid(request: Request) -> str | None:
    """
    For public endpoints that return more to signed-in users. A missing or invalid
    token means an anonymous viewer, so the caller serves only public data.
    """
    try:
        return extract_firebase_user_uid(request)
    except HTTPException:
        return None


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
