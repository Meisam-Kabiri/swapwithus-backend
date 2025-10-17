# import sys
# import os
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_connection.connection_to_db import get_db_connection
import asyncpg
import asyncio


# for image we are using a separate table 
def create_home_table_sql():
    """Return SQL statement to create the 'homes' table."""
    
    return """
  CREATE TABLE IF NOT EXISTS homes (
      -- Primary key and timestamps
      listing_id UUID PRIMARY KEY,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

      -- Owner (from frontend user data)
      owner_firebase_uid VARCHAR(100) NOT NULL,
      email VARCHAR(255) NULL,
      name VARCHAR(200) NULL,
      profile_image VARCHAR(500) NULL,

      -- Step 1: Property Type
      accommodation_type VARCHAR(20) NULL,
      property_type VARCHAR(30) NULL,

      -- Step 2: Capacity & Layout
      max_guests INTEGER NULL,
      bedrooms INTEGER NULL,
      size_input VARCHAR(20) NULL,
      size_unit VARCHAR(10) NULL,
      size_m2 INTEGER NULL,
      surroundings_type VARCHAR(30) NULL,

      -- Step 3: Location
      country VARCHAR(20) NOT NULL,
      city VARCHAR(50) NOT NULL,
      street_address VARCHAR(100) NULL,
      postal_code VARCHAR(20) NULL,
      latitude DECIMAL(10, 8) NULL,
      longitude DECIMAL(11, 8) NULL,
      privacyRadius INTEGER NULL,

  

      -- Step 5: House Rules
      house_rules JSONB NULL,
      main_residence BOOLEAN NULL,

      -- Step 6: Transport & Car Swap
      open_to_car_swap BOOLEAN DEFAULT FALSE,
      require_car_swap_match BOOLEAN DEFAULT FALSE,
      car_details JSONB NULL,

      -- Step 7:  Available Amenities
      amenities JSONB NULL,
      accessibility_features JSONB NULL,
      parking_type VARCHAR(20) NULL,

      -- Step 8: Availability
      is_flexible BOOLEAN NULL,
      available_from DATE NULL,
      available_until DATE NULL,

      -- Step 9: Title and Description
      title VARCHAR(100) NOT NULL,
      description TEXT NULL,

      -- Status
      status VARCHAR(20) DEFAULT 'draft',

      FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE
  );
  
   -- Indexes for users
  CREATE INDEX IF NOT EXISTS idx_homes_owner ON homes(owner_firebase_uid);
  CREATE INDEX IF NOT EXISTS idx_homes_country_city ON homes(country, city);
  CREATE INDEX IF NOT EXISTS idx_homes_created_at ON homes(created_at DESC);


    """
    
def main():
    """Main function to create the 'home' table."""
    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_home_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'home' table created successfully.")
        except Exception as e:
            print(f"❌ Failed to create 'home' table: {e}")
        finally:
            await conn.close()
    
    asyncio.run(run())
    
    
if __name__ == "__main__":
    main()
    
    
    
      
