"""add reshenie_ms, reshenie_kevr, reshenie_kfn, reshenie_nhif act types

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-22
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE act_type ADD VALUE IF NOT EXISTS 'RESHENIE_MS'")
    op.execute("ALTER TYPE act_type ADD VALUE IF NOT EXISTS 'RESHENIE_KEVR'")
    op.execute("ALTER TYPE act_type ADD VALUE IF NOT EXISTS 'RESHENIE_KFN'")
    op.execute("ALTER TYPE act_type ADD VALUE IF NOT EXISTS 'RESHENIE_NHIF'")


def downgrade() -> None:
    pass
