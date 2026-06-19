#!/bin/bash
# One-time: seed local Docker Postgres + Firebase Auth Emulator with fake
# users/listings for manual frontend testing (sign in, browse, message, etc).
set -e

# Always run from the repo root, regardless of where this script was invoked from
# (scripts/dev/seed-local.sh -> repo root is two levels up)
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

echo "🔥 Checking Firebase Auth Emulator at $FIREBASE_AUTH_EMULATOR_HOST ..."
if ! curl -sf -o /dev/null "http://${FIREBASE_AUTH_EMULATOR_HOST}/"; then
  echo "❌ Firebase Auth Emulator not reachable at $FIREBASE_AUTH_EMULATOR_HOST"
  echo "   Start it first in another terminal, then re-run this script:"
  echo "   firebase emulators:start --only auth,firestore --project test-project"
  exit 1
fi

echo "🌱 Seeding fake users + listings (one-time)..."
python scripts/dev/seed_fake_data.py

echo "✅ Done. Postgres data persists in the db_data Docker volume across 'docker compose down'."
