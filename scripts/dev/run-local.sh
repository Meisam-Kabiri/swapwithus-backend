#!/bin/bash
# Run the FastAPI app locally against the local Docker Postgres + Redis.
set -e

# Always run from the repo root, regardless of where this script was invoked from
# (scripts/dev/run-local.sh -> repo root is two levels up)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Docker Compose database credentials (from compose.yaml / scripts/alembic-local.sh)
export SWAPWITHUS_DB_HOST=localhost
export SWAPWITHUS_DB_USER=msm
export SWAPWITHUS_DB_PASSWORD=Mk123456
export SWAPWITHUS_DATABASE_NAME=swapwithusDB
export REDIS_URL=redis://localhost:6379
export FIREBASE_AUTH_EMULATOR_HOST="${FIREBASE_AUTH_EMULATOR_HOST:-localhost:9099}"
export FIRESTORE_EMULATOR_HOST="${FIRESTORE_EMULATOR_HOST:-localhost:8081}"

# Local Google Cloud Storage emulator (fake-gcs-server). These env vars MUST be
# set only locally - in prod (Cloud Run) they are unset and the app talks to real
# GCS. STORAGE_EMULATOR_HOST routes all data-plane calls to the emulator;
# LOCAL_GCS_SIGNING_KEY is a throwaway key used only to sign URLs offline.
export STORAGE_EMULATOR_HOST="${STORAGE_EMULATOR_HOST:-http://localhost:4443}"
export GOOGLE_CLOUD_STORAGE_BUCKET="${GOOGLE_CLOUD_STORAGE_BUCKET:-swapwithus-listing-images}"
export LOCAL_GCS_SIGNING_KEY="${REPO_ROOT}/.local-gcs-sa.json"

export IMAGE_URL_MODE="${IMAGE_URL_MODE:-public}"



if ! command -v firebase >/dev/null 2>&1; then
  echo "Firebase CLI is required but was not found in PATH." >&2
  exit 1
fi

echo "🐳 Starting local Docker Postgres + Redis..."
docker compose up -d

echo "⏳ Waiting for Postgres to be healthy..."
until [ "$(docker compose ps db --format '{{.Health}}')" = "healthy" ]; do
  sleep 1
done

echo "🪣 Waiting for the GCS emulator..."
until curl -fs "${STORAGE_EMULATOR_HOST}/storage/v1/b?project=local-dev" >/dev/null 2>&1; do
  sleep 1
done

# Generate the throwaway signing key once (gitignored), then ensure the bucket
# exists in the emulator. Creating an existing bucket returns 409 - ignore it.
if [ ! -f "${LOCAL_GCS_SIGNING_KEY}" ]; then
  echo "🔑 Generating throwaway local GCS signing key..."
  python "${REPO_ROOT}/scripts/dev/gen-local-gcs-key.py" "${LOCAL_GCS_SIGNING_KEY}"
fi

echo "🪣 Ensuring bucket '${GOOGLE_CLOUD_STORAGE_BUCKET}' exists in the emulator..."
curl -fs -X POST "${STORAGE_EMULATOR_HOST}/storage/v1/b?project=local-dev" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"${GOOGLE_CLOUD_STORAGE_BUCKET}\"}" >/dev/null 2>&1 || true

echo "📦 Applying migrations..."
./scripts/alembic-local.sh upgrade head

FIREBASE_DATA_DIR="${REPO_ROOT}/.firebase-emulator-data"
FIREBASE_ARGS=(
  emulators:exec
  --only auth,firestore
  --project test-project
  --export-on-exit "${FIREBASE_DATA_DIR}"
)

if [ -f "${FIREBASE_DATA_DIR}/firebase-export-metadata.json" ]; then
  echo "📥 Restoring persisted Firebase emulator data..."
  FIREBASE_ARGS+=(--import "${FIREBASE_DATA_DIR}")
else
  echo "🆕 No Firebase emulator export found; starting with empty emulator data."
fi

echo "🔥 Starting Firebase Auth and Firestore emulators..."
echo "🚀 Starting uvicorn on http://localhost:8000 ..."
exec firebase "${FIREBASE_ARGS[@]}" \
  "uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
