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
export FIREBASE_AUTH_EMULATOR_HOST="${FIREBASE_AUTH_EMULATOR_HOST:-localhost:9099}"

echo "🐳 Starting local Docker Postgres + Redis..."
docker compose up -d

echo "⏳ Waiting for Postgres to be healthy..."
until [ "$(docker compose ps db --format '{{.Health}}')" = "healthy" ]; do
  sleep 1
done

echo "📦 Applying migrations..."
./scripts/alembic-local.sh upgrade head

echo "🚀 Starting uvicorn on http://localhost:8000 ..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
