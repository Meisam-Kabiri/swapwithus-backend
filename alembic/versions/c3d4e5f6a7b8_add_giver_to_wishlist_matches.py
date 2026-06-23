"""add giver to wishlist_matches (for swap-chain edges)

Revision ID: c3d4e5f6a7b8
Revises: b8f2c1a4d9e7
Create Date: 2026-06-22 00:00:00.000000

A wishlist match already records the WANTER (wanter_firebase_uid = wishlist owner)
and the listing. To turn matches into swap-chain edges we also need the GIVER -
the listing's owner. The matcher knows it at match time; this column stores it so
cycle detection can build edges (giver -> wanter) without a per-category join.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b8f2c1a4d9e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE wishlist_matches
        ADD COLUMN IF NOT EXISTS giver_firebase_uid VARCHAR(128);

        CREATE INDEX IF NOT EXISTS idx_wishlist_matches_giver
            ON wishlist_matches(giver_firebase_uid);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_wishlist_matches_giver;
        ALTER TABLE wishlist_matches DROP COLUMN IF EXISTS giver_firebase_uid;
    """)
