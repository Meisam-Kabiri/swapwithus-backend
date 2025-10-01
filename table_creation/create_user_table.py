import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connection_to_db import get_db_connection
import asyncpg
import asyncio


# for image we are using a separate table 
def create_users_table_sql():
    """Return SQL statement to create the 'users' table."""

    return """
  
    CREATE TABLE IF NOT EXISTS users (
    firebase_uid VARCHAR(128) PRIMARY KEY NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone_number VARCHAR(50),
    phone_contry_code VARCHAR(10),
    avatar_url VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bank_verified BOOLEAN DEFAULT FALSE,
    email_verified BOOLEAN DEFAULT FALSE,
    phone_verified BOOLEAN DEFAULT FALSE
    );

    """
      
    
def main():
    """Main function to create the 'users' table."""
    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_users_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'users' table created successfully.")
        except Exception as e:
            print(f"❌ Failed to create 'users' table: {e}")
        finally:
            await conn.close()
    
    asyncio.run(run())
    
    
if __name__ == "__main__":
    main()
    