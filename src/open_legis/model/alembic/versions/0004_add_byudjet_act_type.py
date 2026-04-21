"""add byudjet act type

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-21
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE act_type ADD VALUE IF NOT EXISTS 'BYUDJET'")


def downgrade() -> None:
    op.execute("UPDATE work SET act_type = 'ZAKON' WHERE act_type = 'BYUDJET'")
