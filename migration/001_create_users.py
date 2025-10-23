# import sys
# import os
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_db_connection
import asyncio


# for image we are using a separate table
def create_users_table_sql():
    """Return SQL statement to create the 'users' table."""

    return """
  
    CREATE TABLE IF NOT EXISTS users (
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

      owner_firebase_uid VARCHAR(128) PRIMARY KEY,
      email VARCHAR(255) NOT NULL UNIQUE,
      name VARCHAR(200),
      profile_image VARCHAR(500),

      phone_country_code VARCHAR(10),
      phone_number VARCHAR(50),
      is_email_verified BOOLEAN DEFAULT FALSE,

      linkedin_url VARCHAR(255),
      instagram_id VARCHAR(100),
      facebook_id VARCHAR(100),

      is_banking_verified BOOLEAN DEFAULT FALSE,
      is_phone_verified BOOLEAN DEFAULT FALSE
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
