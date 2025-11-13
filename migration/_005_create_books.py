# import sys
# import os
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from app.database.connection import get_db_connection


# for image we are using a separate table
def create_books_table_sql():
    """Return SQL statement to create the 'books' table."""

    return """
  CREATE TABLE IF NOT EXISTS books (
      -- Primary key and timestamps
      listing_id UUID PRIMARY KEY,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

      -- Owner (from frontend user data)
      owner_firebase_uid VARCHAR(100) NOT NULL,
      email VARCHAR(255) NULL,

      -- Step 1: Property Type
      title VARCHAR(100) NOT NULL,
      author VARCHAR(100) NOT NULL,
      format VARCHAR(20) NOT NULL,
      language VARCHAR(20) NOT NULL,
      condition VARCHAR(20) NULL,
      description TEXT NULL,
      publication_year INTEGER NULL,

      -- Step 2: Capacity & Layout
      country VARCHAR(20) NOT NULL,
      city VARCHAR(50) NOT NULL,
      exchange_method VARCHAR(30) NOT NULL,
      exchange_mode VARCHAR(30) NOT NULL,

      -- Step 3: Location
      genre_tags TEXT[] default '{}',


      FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE
  );
  
   -- Indexes for users
  CREATE INDEX IF NOT EXISTS idx_books_owner ON books(owner_firebase_uid);
  CREATE INDEX IF NOT EXISTS idx_books_country_city ON books(country, city);
  CREATE INDEX IF NOT EXISTS idx_books_created_at ON books(created_at DESC);


    """


def main():
    """Main function to create the 'home' table."""

    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_books_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'books' table created successfully.")
        except Exception as e:
            print(f"❌ Failed to create 'home' table: {e}")
        finally:
            await conn.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
