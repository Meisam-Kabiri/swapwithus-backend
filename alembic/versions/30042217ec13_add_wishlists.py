"""add wishlists and wishlist matches

Revision ID: 30042217ec13
Revises: 4cd7dfee7508
Create Date: 2026-06-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30042217ec13'
down_revision: Union[str, Sequence[str], None] = '4cd7dfee7508'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add wishlist support:
    - wishlists: what a user is looking for, per category
    - wishlist_matches: listings that matched a wishlist, feeding the "reveal moment" UI
    """

    op.execute("""
        CREATE TABLE IF NOT EXISTS wishlists (
            wishlist_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_firebase_uid VARCHAR(128) NOT NULL,
            category VARCHAR(20) NOT NULL CHECK (category IN ('homes', 'books', 'clothes', 'caravans')),

            keywords TEXT[] NOT NULL DEFAULT '{}',
            filters JSONB NOT NULL DEFAULT '{}',

            status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused')),

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            FOREIGN KEY (owner_firebase_uid) REFERENCES users(owner_firebase_uid) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_wishlists_owner ON wishlists(owner_firebase_uid);
        CREATE INDEX IF NOT EXISTS idx_wishlists_category_status ON wishlists(category, status);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS wishlist_matches (
            match_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wishlist_id UUID NOT NULL REFERENCES wishlists(wishlist_id) ON DELETE CASCADE,

            listing_id UUID NOT NULL,
            category VARCHAR(20) NOT NULL,

            -- denormalized for a fast "my matches" lookup without joining wishlists
            owner_firebase_uid VARCHAR(128) NOT NULL REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,

            matched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            seen_at TIMESTAMPTZ,

            UNIQUE (wishlist_id, listing_id)
        );

        CREATE INDEX IF NOT EXISTS idx_wishlist_matches_owner ON wishlist_matches(owner_firebase_uid, seen_at);
        CREATE INDEX IF NOT EXISTS idx_wishlist_matches_listing ON wishlist_matches(listing_id);
    """)


def downgrade() -> None:
    """Drop wishlist tables"""
    op.execute("""
        DROP TABLE IF EXISTS wishlist_matches CASCADE;
        DROP TABLE IF EXISTS wishlists CASCADE;
    """)
