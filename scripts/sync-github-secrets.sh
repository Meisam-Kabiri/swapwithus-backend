#!/usr/bin/env bash
# ==============================================================================
# Sync Secrets from 'pass' (Password Store) to GitHub Repository Secrets
# ==============================================================================
set -Eeuo pipefail

# Ensure gh CLI is authenticated
if ! gh auth status >/dev/null 2>&1; then
    echo "❌ GitHub CLI (gh) is not logged in. Please run: gh auth login" >&2
    exit 1
fi

echo "🔐 Reading secrets from pass (password store)..."

# 1. Sync GCP_PROJECT_ID
PROJECT_ID="$(pass show swapwithus/prod/gcp/GCP_PROJECT_ID)"
if [[ -n "${PROJECT_ID}" ]]; then
    gh secret set GCP_PROJECT_ID --body "${PROJECT_ID}"
    echo "✅ Successfully synced GCP_PROJECT_ID to GitHub Secrets"
else
    echo "⚠️ Warning: swapwithus/prod/gcp/GCP_PROJECT_ID in pass was empty" >&2
fi

# 2. Sync GCP_SA_KEY
if pass show swapwithus/prod/gcp/swapwithus-sa-key >/dev/null 2>&1; then
    pass show swapwithus/prod/gcp/swapwithus-sa-key | gh secret set GCP_SA_KEY
    echo "✅ Successfully synced GCP_SA_KEY to GitHub Secrets"
else
    echo "⚠️ Warning: swapwithus/prod/gcp/swapwithus-sa-key not found in pass" >&2
fi

echo "🎉 All GitHub repository secrets synced successfully!"
