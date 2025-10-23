import os

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from firebase_admin import auth as firebase_auth  # type: ignore
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
# redis_client = Redis.from_url(redis_url, decode_responses=True)


def get_user_or_ip(request: Request) -> str:
    """
    Get unique identifier for rate limiting.
    Verify Firebase token and extract UID, or fallback to IP.
    """
    auth_header = request.headers.get("Authorization")

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split("Bearer ")[1]
        try:
            # Verify and decode the Firebase token to get real UID
            decoded_token = firebase_auth.verify_id_token(token)
            uid = decoded_token["uid"]
            return f"user:{uid}"
        except Exception:
            # Invalid token, fallback to IP
            pass  # Fall through to IP-based limiting

    # Fallback to IP for unauthenticated users or invalid tokens
    return f"ip:{get_remote_address(request)}"


# Universal limiter: Uses user UID for authenticated requests, IP for anonymous
limiter = Limiter(
    key_func=get_user_or_ip,  # ✅ Automatically uses UID if authenticated, IP if not
    default_limits=["200 per day", "50 per hour"],
    storage_uri=redis_url,
)


# Custom rate limit exceeded handler
def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    # Try to parse seconds from detail string
    retry_seconds = 60  # Default to 60 seconds

    # Extract time period from detail (e.g., "1 minute", "1 hour")
    if "minute" in str(exc.detail):
        retry_seconds = 60
    elif "hour" in str(exc.detail):
        retry_seconds = 3600
    elif "day" in str(exc.detail):
        retry_seconds = 86400
    elif "second" in str(exc.detail):
        retry_seconds = 1

    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "message": f"Too many requests. Please try again in {retry_seconds} seconds.",
            "retry_after": retry_seconds,
        },
        headers={"Retry-After": str(retry_seconds)},
    )
