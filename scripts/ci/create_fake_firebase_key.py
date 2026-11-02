"""Write a Firebase service account file with a freshly generated key that has no access to anything."""

import json
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()

with open(sys.argv[1], "w") as f:
    json.dump(
        {
            "type": "service_account",
            "project_id": "ci-test-project",
            "private_key_id": "ci",
            "private_key": pem,
            "client_email": "ci@ci-test-project.iam.gserviceaccount.com",
            "client_id": "0",
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        f,
    )
