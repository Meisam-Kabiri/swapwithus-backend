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

if __name__ == "__main__":

  cookie_value = generate_signed_cookie()
  import requests

  url = "https://cdn.swapwithus.com/home/e16f5404-ef8a-4c0e-a698-0492aa811cfe_20251005_52cfedbc-b7d.jpg"

  response = requests.get(url, cookies={"Cloud-CDN-Cookie": cookie_value})
  print(f"Status: {response.status_code} - {'SUCCESS' if response.status_code == 200 else 'FAILED'}")

