#!/usr/bin/env bash

set -Eeuo pipefail

BACKEND_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-${BACKEND_DIR}/../swapwithus-web}"
BACKEND_PORT=8000
FRONTEND_PORT="${FRONTEND_PORT:-8080}"

if [[ ! -f "${FRONTEND_DIR}/package.json" ]]; then
    echo "Frontend not found at: ${FRONTEND_DIR}" >&2
    echo "Set FRONTEND_DIR if it is located elsewhere." >&2
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required but was not found in PATH." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required but was not found in PATH." >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose is required but is not available." >&2
    exit 1
fi

if [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    BACKEND_PYTHON="${BACKEND_DIR}/.venv/bin/python"
elif [[ -x "${HOME}/miniconda3/envs/swapwithus/bin/python" ]]; then
    BACKEND_PYTHON="${HOME}/miniconda3/envs/swapwithus/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    BACKEND_PYTHON="$(command -v python3)"
else
    echo "Python 3 is required but was not found." >&2
    exit 1
fi

if ! command -v setsid >/dev/null 2>&1; then
    echo "setsid is required but was not found in PATH." >&2
    exit 1
fi

port_is_in_use() {
    local port=$1
    [[ -n "$(ss -H -ltn "sport = :${port}" 2>/dev/null)" ]]
}

if ! command -v ss >/dev/null 2>&1; then
    echo "ss is required but was not found in PATH." >&2
    exit 1
fi

if port_is_in_use "${BACKEND_PORT}"; then
    echo "Cannot start: backend port ${BACKEND_PORT} is already in use." >&2
    echo "Inspect it with: ss -ltnp 'sport = :${BACKEND_PORT}'" >&2
    exit 1
fi

if port_is_in_use "${FRONTEND_PORT}"; then
    echo "Cannot start: frontend port ${FRONTEND_PORT} is already in use." >&2
    echo "Inspect it with: ss -ltnp 'sport = :${FRONTEND_PORT}'" >&2
    exit 1
fi

backend_pid=""
frontend_pid=""

cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM

    echo
    echo "Stopping frontend and backend..."

    # Each service has its own session/process group. Terminate the entire
    # group so npm's Next.js child cannot remain running after this script exits.
    [[ -z "${frontend_pid}" ]] || kill -TERM -- "-${frontend_pid}" 2>/dev/null || true
    # SIGINT lets Firebase export Auth/Firestore data before shutting down.
    [[ -z "${backend_pid}" ]] || kill -INT -- "-${backend_pid}" 2>/dev/null || true

    [[ -z "${frontend_pid}" ]] || wait "${frontend_pid}" 2>/dev/null || true
    [[ -z "${backend_pid}" ]] || wait "${backend_pid}" 2>/dev/null || true

    exit "${exit_code}"
}

trap cleanup EXIT INT TERM

echo "Starting complete local backend (PostgreSQL, Redis, migrations, and API)"
(
    cd "${BACKEND_DIR}"
    export PATH="$(dirname "${BACKEND_PYTHON}"):${PATH}"
    exec setsid ./scripts/dev/run-local.sh
) &
backend_pid=$!

echo "Starting frontend at http://localhost:${FRONTEND_PORT}"
(
    cd "${FRONTEND_DIR}"
    export NEXT_PUBLIC_USE_FIREBASE_EMULATORS=true
    export NEXT_PUBLIC_FIREBASE_EMULATOR_HOST=127.0.0.1
    exec setsid npm run dev -- --port "${FRONTEND_PORT}"
) &
frontend_pid=$!

echo "Both services are running. Press Ctrl+C to stop them."

# Stop the other service if either process exits unexpectedly.
wait -n "${backend_pid}" "${frontend_pid}"
