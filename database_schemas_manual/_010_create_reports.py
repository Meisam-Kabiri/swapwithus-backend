import asyncio

from app.database.connection import get_db_connection


def create_reports_table_sql():
    """Return SQL statement to create the 'reports' table."""

    return """

    CREATE TABLE IF NOT EXISTS reports (
        id SERIAL PRIMARY KEY,
        reporter_uid VARCHAR(128) NOT NULL,
        reported_uid VARCHAR(128),
        reported_listing_id UUID,
        reported_swap_id UUID,
        reported_message_id TEXT,
        report_type TEXT NOT NULL CHECK (report_type IN ('spam', 'scam', 'inappropriate', 'harassment', 'fraud', 'other')),
        description TEXT NOT NULL,
        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'in_review', 'resolved', 'dismissed')),
        resolution_action TEXT CHECK (resolution_action IN ('dismiss', 'warn', 'ban_user', 'delete_content', 'other')),
        resolution_notes TEXT,
        resolved_by VARCHAR(128),
        resolved_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),

        -- Foreign keys
        CONSTRAINT fk_reporter FOREIGN KEY (reporter_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,
        CONSTRAINT fk_reported_user FOREIGN KEY (reported_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,
        CONSTRAINT fk_reported_swap FOREIGN KEY (reported_swap_id) REFERENCES swaps(swap_id) ON DELETE CASCADE,
        CONSTRAINT fk_resolved_by FOREIGN KEY (resolved_by) REFERENCES users(owner_firebase_uid) ON DELETE SET NULL,

        -- At least one reported item must be specified
        CONSTRAINT chk_report_target CHECK (
            reported_uid IS NOT NULL OR
            reported_listing_id IS NOT NULL OR
            reported_swap_id IS NOT NULL OR
            reported_message_id IS NOT NULL
        )
    );

    -- Create indexes for better query performance
    CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
    CREATE INDEX IF NOT EXISTS idx_reports_reporter ON reports(reporter_uid);
    CREATE INDEX IF NOT EXISTS idx_reports_reported_user ON reports(reported_uid);
    CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at);
    CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin);
    CREATE INDEX IF NOT EXISTS idx_users_is_banned ON users(is_banned);

    -- Add check constraint to prevent users from reporting themselves (via trigger)
    CREATE OR REPLACE FUNCTION check_self_report() RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.reporter_uid = NEW.reported_uid THEN
            RAISE EXCEPTION 'Cannot report yourself';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS prevent_self_report ON reports;
    CREATE TRIGGER prevent_self_report
        BEFORE INSERT OR UPDATE ON reports
        FOR EACH ROW
        EXECUTE FUNCTION check_self_report();

    """


def main():
    """Main function to create the 'reports' table."""

    async def run():
        conn = await get_db_connection()
        try:
            create_table_sql = create_reports_table_sql()
            await conn.execute(create_table_sql)
            print("✅ 'reports' table created successfully.")
            print("   - Created reports table with constraints")
            print("   - Created indexes for performance")
            print("   - Created self-report prevention trigger")
        except Exception as e:
            print(f"❌ Failed to create 'reports' table: {e}")
        finally:
            await conn.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
