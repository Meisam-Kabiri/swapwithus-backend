#!/bin/bash
# Run Alembic against local Docker Compose database

# Docker Compose database credentials (from compose.yaml)
export SWAPWITHUS_DB_HOST=localhost
export SWAPWITHUS_DB_USER=msm
export SWAPWITHUS_DB_PASSWORD=Mk123456
export SWAPWITHUS_DATABASE_NAME=swapwithusDB

echo "🐳 Running Alembic against LOCAL Docker Compose database"
alembic "$@"
