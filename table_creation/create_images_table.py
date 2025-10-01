import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connection_to_db import get_db_connection
import asyncpg
import asyncio


# for image we are using a separate table 
def create_images_table_sql():
    """Return SQL statement to create the 'images' table."""

    return """
    CREATE TABLE IF NOT EXISTS images (
      
      id SERIAL PRIMARY KEY,
      firebase_uid VARCHAR(100) NOT NULL,
      listing_id UUID NOT NULL,           -- References any category's listing
      category VARCHAR(20) NOT NULL,       -- 'home', 'clothes', 'books', etc.
      cdn_url VARCHAR(500) NOT NULL,
      filename VARCHAR(255) NOT NULL,
      tag VARCHAR(100) NULL,           -- 'bedroom', 'kitchen' (for homes) or 'front', 'back' (for clothes)
      description TEXT NULL,
      sort_order INTEGER DEFAULT 0,
      is_hero BOOLEAN DEFAULT FALSE,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """
      
    
def main():
    """Main function to create the 'images' table."""
    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_images_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'images' table created successfully.")
        except Exception as e:
            print(f"❌ Failed to create 'images' table: {e}")
        finally:
            await conn.close()
    
    asyncio.run(run())
    
    
if __name__ == "__main__":
    main()
    