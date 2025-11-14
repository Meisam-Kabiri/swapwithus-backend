from app.services.gcp_image_service import  get_signed_url
import requests
from app.utils.cdn_auth import make_urlprefix_token

public_url = "https://storage.googleapis.com/swapwithus-listing-images/test_images/hero_page.png"

def test_signed_url_access():
    response = requests.head(public_url, allow_redirects=True)
    assert response.status_code in (401, 403)
    signed_url = get_signed_url(public_url, expires_seconds=3600)
    print("Signed URL:", signed_url)
    response = requests.head(signed_url, allow_redirects=True)
    assert response.status_code == 200

def test_cdn_token_access():
    response = requests.head(public_url, allow_redirects=True)
    assert response.status_code in (401, 403)
    tokenized_url = make_urlprefix_token("https://cdn.swapwithus.com/home/")
    full_signed_url = f"https://cdn.swapwithus.com/test_images/hero_page.png?{tokenized_url}"
    print("Tokenized URL:", full_signed_url)
    response = requests.head(full_signed_url, allow_redirects=True)
    assert response.status_code == 200