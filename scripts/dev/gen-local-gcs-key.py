#!/usr/bin/env python3
"""
Generate a throwaway service-account key used ONLY to sign GCS URLs locally
against fake-gcs-server.

This is NOT a real Google credential and grants no access to anything. The
emulator does not verify signatures; we just need a private key so the storage
client can produce a V4 signature offline. Never use this in prod.

Usage: gen-local-gcs-key.py <output-path>   (no-op if the file already exists)
"""
import json
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main(out_path: str) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_key_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ) if hasattr(key, "private_key_bytes") else key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    sa = {
        "type": "service_account",
        "project_id": "local-dev",
        "private_key_id": "local-dev-key",
        "private_key": pem.decode("utf-8"),
        "client_email": "local-dev@local-dev.iam.gserviceaccount.com",
        "client_id": "0",
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    with open(out_path, "w") as f:
        json.dump(sa, f, indent=2)
    print(f"Wrote throwaway local GCS signing key to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: gen-local-gcs-key.py <output-path>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
