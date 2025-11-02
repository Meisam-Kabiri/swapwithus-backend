import os

import firebase_admin  # type: ignore
from fastapi import HTTPException, Request
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

# Initialize Firebase Admin (only once)
if not firebase_admin._apps:
    # Try absolute path first (Docker), then relative path (local)
    import os

    if os.path.exists("/app/project-8300-firebase-adminsdk.json"):
        cred = credentials.Certificate("/app/project-8300-firebase-adminsdk.json")
    else:
        cred = credentials.Certificate("./project-8300-firebase-adminsdk.json")
    firebase_admin.initialize_app(cred)


def verify_firebase_token(request: Request) -> str:
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
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def verify_user_owns_resource(request: Request, claimed_uid: str):
    """
    Verify that the authenticated user matches the claimed UID
    """
    actual_uid = verify_firebase_token(request)

    if actual_uid != claimed_uid:
        raise HTTPException(
            status_code=403, detail="You don't have permission to access this resource"
        )

    return actual_uid


# TODO:
# Problems with this approach:
# - ⚠️ If you share the Docker image, the secret is inside
# - ⚠️ Hard to rotate the key without rebuilding the image
# - ⚠️ Not following security best practices

# ---
# ✅ Option 2: Use Google Cloud Secret Manager (BETTER - Recommended)

# Store the JSON content as a secret in Google Cloud:

# Step 1: Upload JSON to Secret Manager

# # From your local machine
# gcloud secrets create firebase-service-account \
#     --data-file=firebase-service-account.json \
#     --project=project-8300

# Step 2: Grant Cloud Run access to the secret

# gcloud secrets add-iam-policy-binding firebase-service-account \
#     --member=serviceAccount:YOUR-PROJECT-NUMBER-compute@developer.gserviceaccount.com \
#     --role=roles/secretmanager.secretAccessor

# Step 3: Mount secret in Cloud Run

# When deploying:
# gcloud run deploy your-service \
#     --image=gcr.io/project-8300/your-image \
#     --set-secrets=FIREBASE_CREDS=firebase-service-account:latest

# Step 4: Use it in your code

# import json
# import os
# from firebase_admin import credentials

# # Read from environment variable (Cloud Run injects it)
# firebase_creds = json.loads(os.getenv("FIREBASE_CREDS"))
# cred = credentials.Certificate(firebase_creds)
# firebase_admin.initialize_app(cred)

# ---
# ✅✅ Option 3: Use Workload Identity (BEST - No JSON needed!)

# Since you're on Google Cloud Run, you can avoid the JSON file entirely:

# Step 1: Enable Workload Identity on your Cloud Run service

# Step 2: Use Application Default Credentials

# from firebase_admin import credentials

# # No JSON file needed! Uses Cloud Run's service account
# cred = credentials.ApplicationDefault()
# firebase_admin.initialize_app(cred)

# Step 3: Grant permissions

# Make sure your Cloud Run service account has the Firebase Admin role.

# ---
# My Recommendation:

# For now (quick fix):
# - ✅ Use Option 1 (include in Docker) - gets you working fast
# - ✅ Make sure it's in .gitignore

# Later (proper security):
# - ✅ Migrate to Option 3 (Workload Identity) - cleanest approach
# - OR use Option 2 (Secret Manager) if you need more control


# TODO
# 3. Why send UID in URL? Why not extract from auth header only?

#   You're 100% RIGHT about this one! This is actually a security improvement you should make.

#   Current (less secure):

#   fetch(`/api/users/${user.uid}`, {
#     headers: { Authorization: `Bearer ${token}` }
#   })

#   Better approach:

#   // Frontend - no UID in URL
#   fetch(`/api/users/me`, {
#     headers: { Authorization: `Bearer ${token}` }
#   })

#   // Backend - extract UID from token
#   @app.get("/api/users/me")
#   async def get_my_profile(request: Request):
#       uid = await verify_firebase_token(request)  # Extract UID from token
#       # Fetch user data using uid from token

#   Why this is better:
#   - ✅ No way to manipulate URL to try accessing other users
#   - ✅ Single source of truth (token)
#   - ✅ Cleaner API design
#   - ✅ Less chance of bugs (can't accidentally mismatch UID in URL vs token)

#   For /api/homes?owner_firebase_uid={uid} - same thing, should be:
#   @app.get("/api/homes/my-listings")
#   async def get_my_listings(request: Request):
#       uid = await verify_firebase_token(request)  # Get from token, not query param

#   Want me to refactor this? It's a good security improvemen
