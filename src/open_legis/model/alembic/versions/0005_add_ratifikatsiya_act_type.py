"""add ratifikatsiya act type

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-21
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE act_type ADD VALUE IF NOT EXISTS 'RATIFIKATSIYA'")


def downgrade() -> None:
    pass
