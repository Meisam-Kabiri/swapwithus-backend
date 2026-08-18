"""
CDN URL Utilities for SwapWithUs.
Cloudflare Worker + HMAC handles origin authentication and edge caching.
"""

def build_cdn_image_url(public_url: str, category: str) -> str:
    """Build clean CDN URL for an image from its storage public URL."""
    if not public_url:
        return ""
    if "swapwithus-listing-images/" in public_url:
        blob_path = public_url.split("swapwithus-listing-images/")[-1]
        return f"https://cdn.swapwithus.com/{blob_path}"
    return f"https://cdn.swapwithus.com/{category}/{public_url}"
