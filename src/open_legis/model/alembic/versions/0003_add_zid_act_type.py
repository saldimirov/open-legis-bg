"""add zid act type

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-21
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE act_type ADD VALUE IF NOT EXISTS 'ZID'")


def downgrade() -> None:
    # Postgres does not support removing enum values; reclassify then recreate
    op.execute("UPDATE work SET act_type = 'zakon' WHERE act_type = 'zid'")
