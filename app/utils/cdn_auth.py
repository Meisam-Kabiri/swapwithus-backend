import base64
import hashlib
import hmac
import os
import time

import requests

signing_key = os.getenv("GOOGLE_CLOUD_CDN_SIGNING_KEY")  # Base64-encoded key
key_name = os.getenv("GOOGLE_CLOUD_CDN_KEY_NAME")  # Key name in Cloud CDN

# How listing-image URLs are served. Flip this ONE env var to switch the whole
# app between time-limited signed CDN URLs and plain public CDN URLs - no code
# change, fully reversible.
#   "signed" (default): current behaviour, URLs carry a short-lived token.
#   "public":           URLs are returned bare; set this ONLY after the bucket +
#                       Cloud CDN are made publicly readable (otherwise images 403).
# To roll back to signing, set it to "signed" and re-lock the bucket/CDN.
IMAGE_URL_MODE = (os.getenv("IMAGE_URL_MODE") or "signed").strip().lower()


def images_are_public() -> bool:
    return IMAGE_URL_MODE == "public"


def generate_signed_cookie(
    url_prefix="https://cdn.swapwithus.com/",
    key_name=key_name,
    signing_key=signing_key,
    expiration=None,
):
    if expiration is None:
        expiration_time = int(time.time()) + 3600  # 1 hour from now
    else:
        expiration_time = int(time.time()) + int(expiration)

    # Base64url encode the URL prefix (remove padding)
    encoded_url_prefix = base64.urlsafe_b64encode(url_prefix.encode()).decode().rstrip("=")

    # Create the policy string with proper format
    policy = f"URLPrefix={encoded_url_prefix}:Expires={expiration_time}:KeyName={key_name}"

    # Decode the base64 signing key and create HMAC-SHA1 signature
    signature = hmac.new(
        base64.urlsafe_b64decode(
            signing_key + "=" * (4 - len(signing_key) % 4)
        ),  # Add padding if needed
        policy.encode(),
        hashlib.sha1,
    ).digest()

    # Base64url encode the signature (remove padding)
    encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    # Final cookie value format
    cookie_value = f"{policy}:Signature={encoded_signature}"

    print(f"Generated signed cookie: {cookie_value}")
    print(f"\nSet as cookie: Cloud-CDN-Cookie={cookie_value}")
    print("Domain: .swapwithus.com")
    print("Path: /")
    print(f"Expires: {expiration_time}")

    return cookie_value


KEY_B64 = os.getenv(
    "GOOGLE_CLOUD_CDN_SIGNING_KEY"
)  # exact content of the key file you attached to the backend
KEY_NAME = os.getenv("GOOGLE_CLOUD_CDN_KEY_NAME")  # e.g., "mykey"


def _b64_any_to_bytes(s: str) -> bytes:
    s = (s or "").strip()
    # urlsafe first (+ padding fix), then fallback
    try:
        return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4))
    except Exception:
        return base64.b64decode(s + "=" * ((4 - len(s) % 4) % 4))


# def sign_cdn_url(
#     cdn_url: str, key_name: str = KEY_NAME, key_b64: str = KEY_B64, expires_in: int = 3600
# ) -> tuple[str, str]:
#     assert urlsplit(cdn_url).scheme in ("https", "http"), "URL must start with http(s)://"
#     key = _b64_any_to_bytes(key_b64)
#     if len(key) < 16:
#         raise ValueError(
#             "Signing key decodes to <16 bytes. Use the exact base64 string you attached as the key file."
#         )

#     exp = int(time.time()) + int(expires_in)
#     sep = "&" if "?" in cdn_url else "?"
#     to_sign = (
#         f"{cdn_url}{sep}Expires={exp}&KeyName={key_name}"  # IMPORTANT: Signature is NOT included
#     )
#     sig = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha1).digest()
#     sig_b64u = base64.urlsafe_b64encode(sig).decode().rstrip("=")  # URL-safe, NO padding
#     return f"{to_sign}&Signature={sig_b64u}", to_sign


KEY_B64 = os.getenv("GOOGLE_CLOUD_CDN_SIGNING_KEY")  # content of the key file you attached
KEY_NAME = os.getenv("GOOGLE_CLOUD_CDN_KEY_NAME")  # e.g., "mykey"


# def sign_cdn_url(
#     url: str, key_name: str = KEY_NAME, key_b64: str = KEY_B64, expires_in: int = 3600
# ) -> str:
#     assert urlsplit(url).scheme in ("https", "http"), "URL must start with http(s)://"
#     key = _b64_any_to_bytes(key_b64)
#     if len(key) < 16:
#         raise ValueError(
#             "Signing key looks wrong (decoded <16 bytes). Use the exact base64 string you attached to the backend."
#         )

#     exp = int(time.time()) + int(expires_in)
#     sep = "&" if "?" in url else "?"
#     to_sign = f"{url}{sep}Expires={exp}&KeyName={key_name}"

#     sig = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha1).digest()
#     sig_b64u = (
#         base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
#     )  # IMPORTANT: no '=' padding
#     return f"{to_sign}&Signature={sig_b64u}"


def make_urlprefix_token(
    url_prefix: str,
    key_name: str | None = KEY_NAME,
    key_b64: str | None = KEY_B64,
    expires_in: int = 10 * 3600,
) -> str:
    """Create a single token that authorizes all URLs starting with url_prefix."""
    if not key_name or not key_b64:
        raise ValueError("KEY_NAME and KEY_B64 must be set")
    key = _b64_any_to_bytes(key_b64)
    exp = int(time.time()) + int(expires_in)
    prefix_b64u = base64.urlsafe_b64encode(url_prefix.encode()).decode().rstrip("=")
    policy = f"URLPrefix={prefix_b64u}&Expires={exp}&KeyName={key_name}"
    sig = hmac.new(key, policy.encode(), hashlib.sha1).digest()
    sig_b64u = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{policy}&Signature={sig_b64u}"


def make_image_url_suffix(url_prefix: str, expires_in: int = 10 * 3600) -> str:
    """Query suffix to append to a CDN image URL, honouring IMAGE_URL_MODE.

    signed mode -> '?<urlprefix-token>'  (time-limited access)
    public mode -> ''                    (served publicly, no token)
    """
    if images_are_public():
        return ""
    return "?" + make_urlprefix_token(url_prefix, expires_in=expires_in)


def build_cdn_image_url(public_url: str, category: str) -> str:
    """Final CDN URL for one image, honouring IMAGE_URL_MODE (signed vs public)."""
    blob_name = public_url.split(f"storage.googleapis.com/swapwithus-listing-images/{category}/")[1]
    base = f"https://cdn.swapwithus.com/{category}/{blob_name}"
    return base + make_image_url_suffix("https://cdn.swapwithus.com/")


def append_token_to_url(cdn_url: str, url_prefix_token: str, category: str) -> str:
    """Append the url_prefix_token to the cdn_url (no token in public mode)."""
    # extract blob name
    blob_name = cdn_url.split(f"storage.googleapis.com/swapwithus-listing-images/{category}/")[1]

    base = f"https://cdn.swapwithus.com/{category}/"
    if images_are_public():
        return f"{base}{blob_name}"
    return f"{base}{blob_name}?{url_prefix_token}"


if __name__ == "__main__":

    cookie_value = generate_signed_cookie()

    url = "https://cdn.swapwithus.com/homes/e16f5404-ef8a-4c0e-a698-0492aa811cfe_20251005_52cfedbc-b7d.jpg"
    url = "https://cdn.swapwithus.com/homes/eb7c5c51-d3bb-4f2f-a983-1728e615129d_20251005_8fe2a9a3-204.jpg"

    response = requests.get(url, cookies={"Cloud-CDN-Cookie": cookie_value})
    print(
        f"Status: {response.status_code} - {'SUCCESS' if response.status_code == 200 else 'FAILED'}"
    )

    # signed_url = sign_cdn_url(url)
    # print(f"Signed URL: {signed_url}")

    urlprefix_token = make_urlprefix_token("https://cdn.swapwithus.com/homes/")
    print(f"URL Prefix Token: {urlprefix_token}")

    full_url_with_token = append_token_to_url(url, urlprefix_token, category="homes")
    print(f"Full URL with Token: {full_url_with_token}")
