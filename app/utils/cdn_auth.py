from email.mime import base
import hmac
import hashlib
import base64
import time
import os

signing_key = os.getenv("GOOGLE_CLOUD_CDN_SIGNING_KEY")  # Base64-encoded key
key_name = os.getenv("GOOGLE_CLOUD_CDN_KEY_NAME")  # Key name in Cloud CDN

def generate_signed_cookie(url_prefix="https://cdn.swapwithus.com/", 
                          key_name=key_name, 
                          signing_key=signing_key, 
                          expiration=None):
    if expiration is None:
        expiration_time = int(time.time()) + 3600  # 1 hour from now
    else:
        expiration_time = int(time.time()) + int(expiration)

    # Base64url encode the URL prefix (remove padding)
    encoded_url_prefix = base64.urlsafe_b64encode(url_prefix.encode()).decode().rstrip('=')

    # Create the policy string with proper format
    policy = f"URLPrefix={encoded_url_prefix}:Expires={expiration_time}:KeyName={key_name}"

    # Decode the base64 signing key and create HMAC-SHA1 signature
    signature = hmac.new(
        base64.urlsafe_b64decode(signing_key + '=' * (4 - len(signing_key) % 4)),  # Add padding if needed
        policy.encode(),
        hashlib.sha1
    ).digest()

    # Base64url encode the signature (remove padding)
    encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip('=')

    # Final cookie value format
    cookie_value = f"{policy}:Signature={encoded_signature}"

    print(f"Generated signed cookie: {cookie_value}")
    print(f"\nSet as cookie: Cloud-CDN-Cookie={cookie_value}")
    print(f"Domain: .swapwithus.com")
    print(f"Path: /")
    print(f"Expires: {expiration_time}")

    return cookie_value




import os, time, hmac, hashlib, base64
from urllib.parse import urlsplit

KEY_B64 = os.getenv("GOOGLE_CLOUD_CDN_SIGNING_KEY")   # exact content of the key file you attached to the backend
KEY_NAME = os.getenv("GOOGLE_CLOUD_CDN_KEY_NAME")     # e.g., "mykey"

def _b64_any_to_bytes(s: str) -> bytes:
    s = (s or "").strip()
    # urlsafe first (+ padding fix), then fallback
    try:
        return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4))
    except Exception:
        return base64.b64decode(s + "=" * ((4 - len(s) % 4) % 4))

def sign_cdn_url(cdn_url: str, key_name: str = KEY_NAME, key_b64: str = KEY_B64, expires_in: int = 3600) -> tuple[str, str]:
    assert urlsplit(cdn_url).scheme in ("https", "http"), "URL must start with http(s)://"
    key = _b64_any_to_bytes(key_b64)
    if len(key) < 16:
        raise ValueError("Signing key decodes to <16 bytes. Use the exact base64 string you attached as the key file.")

    exp = int(time.time()) + int(expires_in)
    sep = '&' if '?' in cdn_url else '?'
    to_sign = f"{cdn_url}{sep}Expires={exp}&KeyName={key_name}"  # IMPORTANT: Signature is NOT included
    sig = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha1).digest()
    sig_b64u = base64.urlsafe_b64encode(sig).decode().rstrip("=")  # URL-safe, NO padding
    return f"{to_sign}&Signature={sig_b64u}", to_sign

import os, time, hmac, hashlib, base64
from urllib.parse import urlsplit

KEY_B64 = os.getenv("GOOGLE_CLOUD_CDN_SIGNING_KEY")   # content of the key file you attached
KEY_NAME = os.getenv("GOOGLE_CLOUD_CDN_KEY_NAME")     # e.g., "mykey"

def _b64_any_to_bytes(s: str) -> bytes:
    s = (s or "").strip()
    # try urlsafe first (handles -_ and missing padding)
    try:
        return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4))
    except Exception:
        # fall back to standard base64 (+/)
        return base64.b64decode(s + "=" * ((4 - len(s) % 4) % 4))

def sign_cdn_url(url: str, key_name: str = KEY_NAME, key_b64: str = KEY_B64, expires_in: int = 3600) -> str:
    assert urlsplit(url).scheme in ("https", "http"), "URL must start with http(s)://"
    key = _b64_any_to_bytes(key_b64)
    if len(key) < 16:
        raise ValueError("Signing key looks wrong (decoded <16 bytes). Use the exact base64 string you attached to the backend.")

    exp = int(time.time()) + int(expires_in)
    sep = '&' if '?' in url else '?'
    to_sign = f"{url}{sep}Expires={exp}&KeyName={key_name}"

    sig = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha1).digest()
    sig_b64u = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")  # IMPORTANT: no '=' padding
    return f"{to_sign}&Signature={sig_b64u}"

  
def make_urlprefix_token(url_prefix: str, key_name: str = KEY_NAME,
                         key_b64: str = KEY_B64, expires_in: int = 10*3600) -> str:
    """Create a single token that authorizes all URLs starting with url_prefix."""
    key = _b64_any_to_bytes(key_b64)
    exp = int(time.time()) + int(expires_in)
    prefix_b64u = base64.urlsafe_b64encode(url_prefix.encode()).decode().rstrip("=")
    policy = f"URLPrefix={prefix_b64u}&Expires={exp}&KeyName={key_name}"
    sig = hmac.new(key, policy.encode(), hashlib.sha1).digest()
    sig_b64u = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{policy}&Signature={sig_b64u}"


def append_token_to_url(cdn_url: str, url_prefix_token: str) -> str:
    """Append the url_prefix_token to the cdn_url."""
    # extract blob name
    blob_name = cdn_url.split("storage.googleapis.com/swapwithus-images-storage/home/")[1]
    
    base = "https://cdn.swapwithus.com/home/"
    return f"{base}{blob_name}?{url_prefix_token}"

  
if __name__ == "__main__":

  cookie_value = generate_signed_cookie()
  import requests

  url = "https://cdn.swapwithus.com/home/e16f5404-ef8a-4c0e-a698-0492aa811cfe_20251005_52cfedbc-b7d.jpg"
  url = "https://cdn.swapwithus.com/home/eb7c5c51-d3bb-4f2f-a983-1728e615129d_20251005_8fe2a9a3-204.jpg"

  response = requests.get(url, cookies={"Cloud-CDN-Cookie": cookie_value})
  print(f"Status: {response.status_code} - {'SUCCESS' if response.status_code == 200 else 'FAILED'}")
  
  signed_url = sign_cdn_url(url)
  print(f"Signed URL: {signed_url}")
  
  urlprefix_token = make_urlprefix_token("https://cdn.swapwithus.com/home/")
  print(f"URL Prefix Token: {urlprefix_token}")
  
  
  full_url_with_token = append_token_to_url(url, urlprefix_token)
  print(f"Full URL with Token: {full_url_with_token}")

