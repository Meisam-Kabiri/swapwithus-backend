import asyncio

from app.database.connection import get_db_connection


def create_swaps_table_sql():
    """Return SQL statement to create the 'swaps' table."""

    return """
    CREATE TABLE IF NOT EXISTS swaps (
      swap_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      category VARCHAR(50) NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  

      -- Participants (users involved in the swap)
      user_a_uid VARCHAR(128) NOT NULL,
      user_b_uid VARCHAR(128) NOT NULL,

      -- Listings being swapped
      listing_a_id UUID NOT NULL,
      listing_b_id UUID NOT NULL,

      -- Listing categories (for easier querying)
      listing_a_category VARCHAR(50),
      listing_b_category VARCHAR(50),

      -- Swap status: 'pending', 'accepted', 'completed', 'cancelled'
      status VARCHAR(50) NOT NULL DEFAULT 'pending',

      -- Reference to the conversation
      conversation_id VARCHAR(128),

      -- Completion tracking (both users must confirm receipt)
      user_a_confirmed BOOLEAN DEFAULT FALSE,
      user_b_confirmed BOOLEAN DEFAULT FALSE,
      completed_at TIMESTAMPTZ,

      -- Important timestamps
      initiated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      accepted_at TIMESTAMPTZ,
      cancelled_at TIMESTAMPTZ,

      -- Cancellation details
      cancelled_by VARCHAR(128) REFERENCES users(owner_firebase_uid),
      cancellation_reason TEXT,
      
      user_a_deleted BOOLEAN DEFAULT FALSE,
      user_b_deleted BOOLEAN DEFAULT FALSE,
      listing_a_deleted BOOLEAN DEFAULT FALSE,
      listing_b_deleted BOOLEAN DEFAULT FALSE,


      -- Check constraints
      CONSTRAINT different_users CHECK (user_a_uid != user_b_uid),
      CONSTRAINT different_listings CHECK (listing_a_id != listing_b_id),
      CONSTRAINT valid_status CHECK (status IN ('pending', 'accepted', 'completed', 'cancelled'))
    );

    -- Indexes for efficient querying
    CREATE INDEX IF NOT EXISTS idx_swaps_user_a ON swaps(user_a_uid);
    CREATE INDEX IF NOT EXISTS idx_swaps_user_b ON swaps(user_b_uid);
    CREATE INDEX IF NOT EXISTS idx_swaps_status ON swaps(status);
    CREATE INDEX IF NOT EXISTS idx_swaps_conversation ON swaps(conversation_id);
    CREATE INDEX IF NOT EXISTS idx_swaps_completed_at ON swaps(completed_at);

    -- Index for finding swaps between two users
    CREATE INDEX IF NOT EXISTS idx_swaps_users ON swaps(user_a_uid, user_b_uid);

    """


def main():
    """Main function to create the 'swaps' table."""

    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_swaps_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'swaps' table created successfully.")
        except Exception as e:
            print(f"❌ Failed to create 'swaps' table: {e}")
        finally:
            await conn.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
