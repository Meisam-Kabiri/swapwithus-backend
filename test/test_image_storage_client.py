from unittest.mock import patch

from app.services import gcp_image_service as service

BUCKET = "swapwithus-listing-images"


def test_upload_and_delete_use_a_real_storage_client(monkeypatch):
    """Guards the upload and delete paths against losing their storage client again."""
    monkeypatch.delenv("STORAGE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_STORAGE_BUCKET", BUCKET)

    with patch.object(service.storage, "Client") as client:
        blob = client.return_value.bucket.return_value.blob.return_value

        service._blocking_upload(b"photo", BUCKET, "homes/a.jpg")
        blob.upload_from_file.assert_called_once()

        assert service._blocking_delete(f"https://storage.googleapis.com/{BUCKET}/homes/a.jpg")
        blob.delete.assert_called_once()


def test_local_runs_use_the_emulator(monkeypatch):
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:4443")

    with patch.object(service.storage, "Client") as client:
        service._get_storage_client()

    assert client.call_args.kwargs["client_options"] == {"api_endpoint": "http://localhost:4443"}
