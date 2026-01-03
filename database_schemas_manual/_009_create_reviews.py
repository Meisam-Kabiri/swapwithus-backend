import asyncio

from app.database.connection import get_db_connection


def create_reviews_table_sql():
    """Return SQL statement to create the 'reviews' table."""

    return """
    CREATE TABLE IF NOT EXISTS reviews (
      review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

      -- Who is reviewing whom
      reviewer_uid VARCHAR(128) NOT NULL REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,
      reviewee_uid VARCHAR(128) NOT NULL REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,

      -- Associated swap (ensures review is from completed swap)
      swap_id UUID NOT NULL REFERENCES swaps(swap_id) ON DELETE CASCADE,

      -- Overall rating (1-5 stars)
      rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),

      -- Review comment (optional)
      comment TEXT,

      -- Detailed ratings (optional, 1-5 stars each)
      communication_rating INTEGER CHECK (communication_rating >= 1 AND communication_rating <= 5),
      item_condition_rating INTEGER CHECK (item_condition_rating >= 1 AND item_condition_rating <= 5),
      timeliness_rating INTEGER CHECK (timeliness_rating >= 1 AND timeliness_rating <= 5),

      -- Prevent reviewing yourself
      CONSTRAINT no_self_review CHECK (reviewer_uid != reviewee_uid),

      -- Prevent duplicate reviews (one review per swap per user)
      UNIQUE(reviewer_uid, swap_id)
    );

    -- Indexes for efficient querying
    CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON reviews(reviewer_uid);
    CREATE INDEX IF NOT EXISTS idx_reviews_reviewee ON reviews(reviewee_uid);
    CREATE INDEX IF NOT EXISTS idx_reviews_swap ON reviews(swap_id);
    CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating);
    CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at DESC);

    """


def main():
    """Main function to create the 'reviews' table."""

    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_reviews_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'reviews' table created successfully.")
        except Exception as e:
            print(f"❌ Failed to create 'reviews' table: {e}")
        finally:
            await conn.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
