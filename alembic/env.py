import os
import urllib.parse
from logging.config import fileConfig

# Automatically load .env file for local Alembic commands
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None

# --- Database URL Configuration (Google Cloud SQL ONLY) ---
# For Docker Compose migrations, use migrate_docker.sh script instead

# Check if running on Cloud Run (K_SERVICE env var is set by Cloud Run)
IS_CLOUD_RUN = os.getenv("K_SERVICE") is not None

# Get database credentials from environment
DB_USER = os.getenv("SWAPWITHUS_DB_USER")
DB_PASSWORD = os.getenv("SWAPWITHUS_DB_PASSWORD")
DB_NAME = os.getenv("SWAPWITHUS_DATABASE_NAME")
DB_HOST = os.getenv("SWAPWITHUS_DB_HOST")  # Cloud SQL public IP
DB_PORT = "5432"

# Validate required env vars
if not all([DB_USER, DB_PASSWORD, DB_NAME]):
    raise ValueError(
        "Missing required SWAPWITHUS database environment variables.\n"
        "This env.py is configured for Google Cloud SQL only.\n"
        "For Docker Compose, use: ./migrate_docker.sh <command>"
    )

# URL encode password to handle special characters
encoded_password = urllib.parse.quote_plus(DB_PASSWORD)

# Build connection string based on Cloud environment
# NOTE: Alembic uses psycopg2 (synchronous), not asyncpg (asynchronous)
if IS_CLOUD_RUN:
    # Cloud Run: Use Unix socket for Cloud SQL Proxy
    CLOUD_SQL_CONNECTION = "swapwithus-project:europe-north1:swapwithus-db"
    # For psycopg2, use postgresql+psycopg2:// driver
    SQLALCHEMY_URL = f"postgresql+psycopg2://{DB_USER}:{encoded_password}@/{DB_NAME}?host=/cloudsql/{CLOUD_SQL_CONNECTION}"
    print("🌩️  Alembic: Cloud Run mode - Connecting via Cloud SQL Proxy")
else:
    # Cloud SQL public IP connection (for local development with Cloud SQL)
    if not DB_HOST:
        raise ValueError(
            "Missing SWAPWITHUS_DB_HOST environment variable.\n"
            "This env.py requires Cloud SQL public IP or Cloud Run.\n"
            "For Docker Compose, use: ./migrate_docker.sh <command>"
        )
    SQLALCHEMY_URL = f"postgresql+psycopg2://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"🌩️  Alembic: Google Cloud SQL mode - Connecting to {DB_HOST}")

# Override the sqlalchemy.url in alembic.ini with our dynamic URL
# Note: We need to escape % signs for ConfigParser by doubling them
config.set_main_option("sqlalchemy.url", SQLALCHEMY_URL.replace("%", "%%"))

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
