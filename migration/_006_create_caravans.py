import asyncio

from app.database.connection import get_db_connection


def create_caravans_table_sql():
    """Return SQL statement to create the 'caravans' table."""

    return """
    CREATE TABLE IF NOT EXISTS caravans (
      listing_id UUID PRIMARY KEY,
      owner_firebase_uid VARCHAR(100) NOT NULL,

      -- Basic Info
      title VARCHAR(200) NOT NULL,
      vehicle_type VARCHAR(20) NOT NULL CHECK (vehicle_type IN ('caravan', 'campervan', 'motorhome')),

      -- Location
      country VARCHAR(100) NOT NULL,
      city VARCHAR(100) NOT NULL,

      -- Capacity
      max_guests INTEGER NOT NULL CHECK (max_guests > 0 AND max_guests <= 20),

      -- Exchange Details
      exchange_method VARCHAR(30) NOT NULL CHECK (exchange_method IN ('pickup_only', 'delivery_possible', 'both')),

      -- Vehicle-specific
      tow_requirement VARCHAR(100),
      drive_license_req VARCHAR(50),

      -- Vehicle Details
      year INTEGER CHECK (year >= 1950 AND year <= 2100),
      make VARCHAR(100),
      model VARCHAR(100),
      condition VARCHAR(20) CHECK (condition IN ('new', 'excellent', 'good', 'fair', 'needs_work')),
      registration_country VARCHAR(100),

      -- For motorized vehicles
      fuel_type VARCHAR(20) CHECK (fuel_type IN ('diesel', 'petrol', 'electric', 'hybrid')),
      transmission VARCHAR(20) CHECK (transmission IN ('manual', 'automatic')),
      mileage_km INTEGER CHECK (mileage_km >= 0),

      -- Dimensions & weight
      length_meters DECIMAL(4,1) CHECK (length_meters > 0 AND length_meters <= 30),
      weight_kg INTEGER CHECK (weight_kg > 0),

      -- Sleeping
      bed_layout VARCHAR(200),
      bed_count INTEGER CHECK (bed_count >= 0 AND bed_count <= 20),

      -- Amenities & Features (JSONB for flexibility)
      amenities JSONB DEFAULT '[]'::jsonb,
      power_source JSONB DEFAULT '[]'::jsonb,
      water_system VARCHAR(200),
      winterized BOOLEAN,

      -- Rules & Policies
      pet_allowed BOOLEAN,
      smoking_allowed BOOLEAN,
      insurance_included BOOLEAN,
      deposit_required INTEGER CHECK (deposit_required >= 0),

      -- Location & Availability
      location_note VARCHAR(500),
      available_from DATE,
      available_until DATE,
      delivery_radius_km INTEGER CHECK (delivery_radius_km >= 0),

      -- Description
      description TEXT,

      -- User info (duplicated for convenience)
      email VARCHAR(255),
      name VARCHAR(100),
      profile_image VARCHAR(500),

      -- Status
      status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),

      -- Timestamps
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW(),

      FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE
    );

    -- Indexes for caravans
    CREATE INDEX IF NOT EXISTS idx_caravans_owner ON caravans(owner_firebase_uid);
    CREATE INDEX IF NOT EXISTS idx_caravans_location ON caravans(country, city);
    CREATE INDEX IF NOT EXISTS idx_caravans_vehicle_type ON caravans(vehicle_type);
    CREATE INDEX IF NOT EXISTS idx_caravans_status ON caravans(status);
    CREATE INDEX IF NOT EXISTS idx_caravans_created_at ON caravans(created_at DESC);
    """


def main():
    """Main function to create the 'caravans' table."""

    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_caravans_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'caravans' table created successfully.")
        except Exception as e:
            print(f"❌ Failed to create 'caravans' table: {e}")
        finally:
            await conn.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
