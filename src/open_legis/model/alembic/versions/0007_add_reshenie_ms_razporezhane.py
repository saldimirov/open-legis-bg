"""add reshenie_ms and razporezhane act types

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-21
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE act_type ADD VALUE IF NOT EXISTS 'RESHENIE_MS'")
    op.execute("ALTER TYPE act_type ADD VALUE IF NOT EXISTS 'RAZPOREZHANE'")


def downgrade() -> None:
    pass  # Postgres does not support removing enum values
