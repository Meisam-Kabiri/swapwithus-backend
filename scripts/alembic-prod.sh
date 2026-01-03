#!/bin/bash
# Run Alembic against Google Cloud SQL production database

export SWAPWITHUS_DB_HOST=${SWAPWITHUS_DB_HOST}
export SWAPWITHUS_DB_NAME=${SWAPWITHUS_DB_NAME}
export SWAPWITHUS_DB_USER=${SWAPWITHUS_DB_USER}
export SWAPWITHUS_DB_PASSWORD=${SWAPWITHUS_DB_PASSWORD}

echo "☁️  Running Alembic against PRODUCTION Google Cloud SQL"
alembic "$@"
