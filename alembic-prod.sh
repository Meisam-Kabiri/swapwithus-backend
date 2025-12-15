#!/bin/bash
# Run Alembic against Google Cloud SQL production database

export SWAPWITHUS_DB_HOST=35.228.209.98

echo "☁️  Running Alembic against PRODUCTION Google Cloud SQL"
alembic "$@"
