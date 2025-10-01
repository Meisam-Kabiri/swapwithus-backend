from sqlalchemy import MetaData, Table, Column, Integer, String, DateTime, Boolean, Text, func
from sqlalchemy.dialects import postgresql
import asyncpg
from connection_to_db import get_db_connection
import asyncio


# SQLAlchemy metadata for schema definition only (NO connections)
metadata = MetaData()

# APPROACH 1: SQLAlchemy Core (recommended for schema)
tb1_table = Table('tb1', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),  # Auto-incrementing primary key
    Column('title', String(255), nullable=False),                 # Required item title, max 255 chars
    Column('description', Text, nullable=True),                   # Optional long description
    Column('owner_id', Integer, nullable=False),                  # Required user who owns the item
    Column('category', String(100), nullable=False, default='general'),  # Item category with default
    Column('status', String(50), nullable=False, default='available'),   # Swap status: available, swapped, etc
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp())  # Auto timestamp
)


async def create_table_sqlalchemy():
    """Create table using SQLAlchemy Core + asyncpg execution"""
    from sqlalchemy.schema import CreateTable
    
    # Generate CREATE TABLE SQL from SQLAlchemy definition (correct way)
    create_sql = str(CreateTable(tb1_table).compile(dialect=postgresql.dialect()))
    
    conn = await get_db_connection()
    try:
        await conn.execute(create_sql)
        print("✅ Table created using SQLAlchemy Core")
        print(f"SQL executed: {create_sql}")
    except Exception as e:
        print(f"❌ SQLAlchemy table creation failed: {e}")
    finally:
        await conn.close()

# APPROACH 2: Pure asyncpg (for learning comparison)
async def create_table_asyncpg():
    """Create identical table using pure asyncpg SQL"""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS items (
        id SERIAL PRIMARY KEY,                                    -- Auto-incrementing primary key
        title VARCHAR(255) NOT NULL,                              -- Required item title, max 255 chars  
        description TEXT,                                         -- Optional long description
        owner_id INTEGER NOT NULL,                                -- Required user who owns the item
        category VARCHAR(100) NOT NULL DEFAULT 'general',        -- Item category with default
        status VARCHAR(50) NOT NULL DEFAULT 'available',         -- Swap status: available, swapped, etc
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP  -- Auto timestamp
    );
    """
    
    conn = await get_db_connection()
    try:
        await conn.execute(create_table_sql)
        print("✅ Table created using pure asyncpg")
    except Exception as e:
        print(f"❌ asyncpg table creation failed: {e}")
    finally:
        await conn.close()
        
        
if __name__ == "__main__":
    # Run both creation methods for comparison
    asyncio.run(create_table_sqlalchemy())
    asyncio.run(create_table_asyncpg())
