import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connection_to_db import get_db_connection
import asyncpg
import asyncio


# for image we are using a separate table 
def create_home_table_sql():
    """Return SQL statement to create the 'homes' table."""
    
    return """
    CREATE TABLE IF NOT EXISTS homes (
      
      listing_id UUID PRIMARY KEY,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

      firebase_uid VARCHAR(100) NOT NULL,

      -- Step 1: Property Type
      accommodationType VARCHAR(20) NULL,
      propertyType VARCHAR(30) NULL,

      -- Step 2: Capacity & Layout
      maxGuests INTEGER NULL,
      bedrooms INTEGER NULL,
      fullBathrooms INTEGER NULL,
      halfBathrooms INTEGER NULL,
      sizeInput VARCHAR(20) NULL,
      sizeUnit VARCHAR(10) NULL,
      sizeM2 INTEGER NULL,
      beds JSONB NULL,

      -- Step 3: Location
      country VARCHAR(20) NOT NULL,
      city VARCHAR(50) NOT NULL,
      streetAddress VARCHAR(100) NULL,
      postalCode VARCHAR(20) NULL,
      latitude DECIMAL(10, 8) NULL,
      longitude DECIMAL(11, 8) NULL,

      -- Step 4: Photos (separate table)

      -- Step 5: Essential Features
      essentials TEXT NULL,
      wifiMbpsDown INTEGER NULL,
      wifiMbpsUp INTEGER NULL,
      surroundingsType VARCHAR(30) NULL,

      -- Step 6: House Rules
      houseRules TEXT NULL,
      mainResidence BOOLEAN NULL,

      -- Step 7: Transport & Car Swap
      openToCarSwap BOOLEAN NULL,
      requireCarSwapMatch BOOLEAN NULL,
      carMakeModelYear VARCHAR(100) NULL,
      carTransmission VARCHAR(20) NULL,
      carFuelType VARCHAR(20) NULL,
      carConnectorType VARCHAR(20) NULL,
      carSeats INTEGER NULL,
      carInsuranceConfirmed BOOLEAN NULL,
      carMinDriverAge INTEGER NULL,
      carMileageLimit INTEGER NULL,
      carPickupNote TEXT NULL,

      -- Step 8: Practical Amenities
      kitchen TEXT NULL,
      laundry TEXT NULL,
      workEntertainment TEXT NULL,
      outdoor TEXT NULL,
      family TEXT NULL,
      comfortClimate TEXT NULL,
      safety TEXT NULL,
      accessibilityFeatures TEXT NULL,
      parkingType VARCHAR(20) NULL,

      -- Step 9: Availability
      isFlexible BOOLEAN NULL,
      availableFrom DATE NULL,
      availableUntil DATE NULL,

      -- Step 10: Title and Description
      title VARCHAR(100) NOT NULL,
      description TEXT NULL,

      -- Status
      status VARCHAR(20) DEFAULT 'draft'
  );

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
    
    
    
      
