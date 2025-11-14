# import sys
# import os
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from app.database.connection import get_db_connection


# for image we are using a separate table
def create_images_table_sql():
    """Return SQL statement to create the 'images' table."""

    return """
    CREATE TABLE IF NOT EXISTS images (
      
      owner_firebase_uid VARCHAR(100) NOT NULL,
      listing_id UUID NOT NULL,           -- References any category's listing
      category VARCHAR(20) NOT NULL,       -- 'home', 'clothes', 'books', etc.
      public_url VARCHAR(500) NOT NULL,
      cdn_url VARCHAR(500) NOT NULL,
      tag VARCHAR(100) NULL,           -- 'bedroom', 'kitchen' (for homes) or 'front', 'back' (for clothes)
      caption TEXT NULL,
      sort_order INTEGER DEFAULT 0,
      is_hero BOOLEAN DEFAULT FALSE,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW(),

      FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,
      -- No FK on listing_id since it can reference homes, books, clothes, etc. tables
      UNIQUE (listing_id, public_url)

    );
    
    -- Indexes for images
    CREATE INDEX IF NOT EXISTS idx_images_listing ON images(listing_id);
    CREATE INDEX IF NOT EXISTS idx_images_owner ON images(owner_firebase_uid);
    CREATE INDEX IF NOT EXISTS idx_images_category_listing ON images(category, listing_id);
    CREATE INDEX IF NOT EXISTS idx_images_sort_order ON images(listing_id, sort_order);

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
