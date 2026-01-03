"""add admin and moderation features

Revision ID: 4cd7dfee7508
Revises: 79f6bb48ee27
Create Date: 2025-12-16 14:35:39.823502

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4cd7dfee7508'
down_revision: Union[str, Sequence[str], None] = '79f6bb48ee27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    """
    Add admin and moderation features:
    - Admin role for users
    - User ban functionality
    - Reports table for content moderation
    """

    # Add admin and ban fields to users table
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS ban_reason TEXT,
        ADD COLUMN IF NOT EXISTS banned_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS ban_duration_days INTEGER,
        ADD COLUMN IF NOT EXISTS last_active TIMESTAMPTZ
    """)

    # Create reports table
    op.execute("""
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
        )
    """)

    # Create indexes for better query performance
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
        CREATE INDEX IF NOT EXISTS idx_reports_reporter ON reports(reporter_uid);
        CREATE INDEX IF NOT EXISTS idx_reports_reported_user ON reports(reported_uid);
        CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at);
        CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin);
        CREATE INDEX IF NOT EXISTS idx_users_is_banned ON users(is_banned);
    """)

    # Add check constraint to prevent users from reporting themselves (via trigger)
    op.execute("""
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
    """)


def downgrade() -> None:
    """
    Rollback admin and moderation features
    """

    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS prevent_self_report ON reports")
    op.execute("DROP FUNCTION IF EXISTS check_self_report()")

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_reports_status")
    op.execute("DROP INDEX IF EXISTS idx_reports_reporter")
    op.execute("DROP INDEX IF EXISTS idx_reports_reported_user")
    op.execute("DROP INDEX IF EXISTS idx_reports_created_at")
    op.execute("DROP INDEX IF EXISTS idx_users_is_admin")
    op.execute("DROP INDEX IF EXISTS idx_users_is_banned")

    # Drop reports table
    op.execute("DROP TABLE IF EXISTS reports CASCADE")

    # Remove admin and ban fields from users
    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS is_admin,
        DROP COLUMN IF EXISTS is_banned,
        DROP COLUMN IF EXISTS ban_reason,
        DROP COLUMN IF EXISTS banned_at,
        DROP COLUMN IF EXISTS ban_duration_days,
        DROP COLUMN IF EXISTS last_active
    """)
