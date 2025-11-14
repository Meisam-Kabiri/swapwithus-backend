import asyncio

from app.database.connection import get_db_connection


def create_clothes_table_sql():
    """Return SQL statement to create the 'clothes' table."""

    return """
    CREATE TABLE IF NOT EXISTS clothes (
      listing_id UUID PRIMARY KEY,
      owner_firebase_uid VARCHAR(100) NOT NULL,

      -- Basic Info
      title VARCHAR(200) NOT NULL,
      clothing_category VARCHAR(30) NOT NULL CHECK (clothing_category IN (
        'tshirt', 'shirt', 'dress', 'trousers', 'jeans', 'coat', 'jacket',
        'sweater', 'hoodie', 'sportswear', 'shoes', 'bag', 'accessory', 'other'
      )),
      size VARCHAR(20) NOT NULL,
      condition VARCHAR(20) NOT NULL CHECK (condition IN ('new', 'like_new', 'very_good', 'good', 'used')),

      -- Location
      city VARCHAR(100) NOT NULL,
      country VARCHAR(100) NOT NULL,

      -- Exchange Details
      exchange_method VARCHAR(30) NOT NULL CHECK (exchange_method IN ('pickup_only', 'shipping_possible', 'both')),

      -- Optional Details
      gender VARCHAR(20) CHECK (gender IN ('women', 'men', 'unisex', 'kids')),
      brand VARCHAR(100),
      color VARCHAR(50),
      material VARCHAR(200),
      season VARCHAR(20) CHECK (season IN ('all', 'spring', 'summer', 'autumn', 'winter')),
      kids_age_range VARCHAR(50),
      fit VARCHAR(20) CHECK (fit IN ('regular', 'oversized', 'slim')),
      defects VARCHAR(500),

      -- Description
      description TEXT,

      -- User info (duplicated for convenience)
      email VARCHAR(255),
      name VARCHAR(100),
      profile_image VARCHAR(500),


      -- Timestamps
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW(),

      FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE
    );

    -- Indexes for clothes
    CREATE INDEX IF NOT EXISTS idx_clothes_owner ON clothes(owner_firebase_uid);
    CREATE INDEX IF NOT EXISTS idx_clothes_location ON clothes(country, city);
    CREATE INDEX IF NOT EXISTS idx_clothes_category ON clothes(clothing_category);
    CREATE INDEX IF NOT EXISTS idx_clothes_size ON clothes(size);
    CREATE INDEX IF NOT EXISTS idx_clothes_gender ON clothes(gender);
    CREATE INDEX IF NOT EXISTS idx_clothes_status ON clothes(status);
    CREATE INDEX IF NOT EXISTS idx_clothes_created_at ON clothes(created_at DESC);
    """


def main():
    """Main function to create the 'clothes' table."""

    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_clothes_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'clothes' table created successfully.")
        except Exception as e:
            print(f"❌ Failed to create 'clothes' table: {e}")
        finally:
            await conn.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
