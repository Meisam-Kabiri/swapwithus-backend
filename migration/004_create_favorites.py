from database.connection import get_db_connection
import asyncpg
import asyncio

def create_favorite_table_sql():
    """Return SQL statement to create the 'favorites' table."""
    
    return """
  CREATE TABLE favorites (
  owner_firebase_uid  VARCHAR(100) NOT NULL REFERENCES users(owner_firebase_uid)  ON DELETE CASCADE,
  listing_id  UUID NOT NULL REFERENCES homes(listing_id) ON DELETE CASCADE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_firebase_uid, listing_id)
);

-- useful for counts & reverse lookups
CREATE INDEX idx_favorites_listing ON favorites(listing_id);


    """
    
def main():
    """Main function to create the 'favorite' table."""
    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_favorite_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'favorite' table created successfully.")
        except Exception as e:
            print(f"❌ Failed to create 'favorite' table: {e}")
        finally:
            await conn.close()
    
    asyncio.run(run())
    
    
if __name__ == "__main__":
    main()
    
    
    
      

