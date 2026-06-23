"""add swap chains and legs (multi-way swaps)

Revision ID: b8f2c1a4d9e7
Revises: 30042217ec13
Create Date: 2026-06-22 00:00:00.000000

Additive only: introduces the multi-way swap model without touching the existing
2-party `swaps` table (which keeps working until the chain API replaces it).

A swap is modelled as one parent chain + N legs:
  - swap_chains: chain-level facts that exist exactly once per swap
                 (status, the group conversation, timestamps).
  - swap_legs:   one row per item handoff (from_user -> to_user). A direct 2-way
                 swap is a chain with 2 legs; a triangular swap has 3; etc.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8f2c1a4d9e7'
down_revision: Union[str, Sequence[str], None] = '30042217ec13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS swap_chains (
            chain_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            -- one status for the WHOLE swap (not per leg)
            status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'accepted', 'completed', 'cancelled')),

            -- the group chat shared by every participant in the chain
            conversation_id VARCHAR(128),

            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at    TIMESTAMPTZ,
            cancelled_at    TIMESTAMPTZ,
            cancelled_by    VARCHAR(128) REFERENCES users(owner_firebase_uid) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_swap_chains_status ON swap_chains(status);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS swap_legs (
            leg_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            chain_id    UUID NOT NULL REFERENCES swap_chains(chain_id) ON DELETE CASCADE,

            -- one item moving: from_user gives listing_id to to_user
            from_user   VARCHAR(128) NOT NULL REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,
            to_user     VARCHAR(128) NOT NULL REFERENCES users(owner_firebase_uid) ON DELETE CASCADE,

            -- listings live in per-category tables, so we store id + category
            -- (no FK possible to a single table); category tells us where to look.
            listing_id  UUID NOT NULL,
            category    VARCHAR(20) NOT NULL,

            -- the GIVER (from_user) agrees to the proposed swap
            accepted    BOOLEAN NOT NULL DEFAULT FALSE,
            accepted_at TIMESTAMPTZ,

            -- the RECEIVER (to_user) confirms they got the item (completion phase)
            received    BOOLEAN NOT NULL DEFAULT FALSE,
            received_at TIMESTAMPTZ,

            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- the same listing can't appear twice in one chain
            UNIQUE (chain_id, listing_id),
            -- you don't hand an item to yourself within a leg
            CONSTRAINT swap_legs_different_users CHECK (from_user != to_user)
        );

        -- chain_id: fetch all legs of a chain.
        CREATE INDEX IF NOT EXISTS idx_swap_legs_chain ON swap_legs(chain_id);
        -- listing_id: critical for conflict detection ("is this item already in a pending chain?").
        CREATE INDEX IF NOT EXISTS idx_swap_legs_listing ON swap_legs(listing_id);
        CREATE INDEX IF NOT EXISTS idx_swap_legs_from_user ON swap_legs(from_user);
        CREATE INDEX IF NOT EXISTS idx_swap_legs_to_user ON swap_legs(to_user);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS swap_legs CASCADE;
        DROP TABLE IF EXISTS swap_chains CASCADE;
    """)
