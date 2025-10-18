import os 
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from redis.asyncio import Redis

from fastapi.responses import JSONResponse
from fastapi import Request, Response

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
# redis_client = Redis.from_url(redis_url, decode_responses=True)



    
    
limiter = Limiter(
    key_func=get_remote_address,
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
    
