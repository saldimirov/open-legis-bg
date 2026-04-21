"""add raw_text and resolved to reference table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reference", sa.Column("raw_text", sa.Text(), nullable=True))
    op.add_column("reference", sa.Column("resolved", sa.Boolean(), nullable=True))
    # Backfill existing rows (none expected, but safe)
    op.execute("UPDATE reference SET raw_text = '' WHERE raw_text IS NULL")
    op.execute("UPDATE reference SET resolved = false WHERE resolved IS NULL")
    op.alter_column("reference", "raw_text", nullable=False)
    op.alter_column("reference", "resolved", nullable=False)
    # Index for re-resolution pass: find all unresolved references quickly
    op.create_index("ix_reference_unresolved", "reference", ["resolved"], postgresql_where=sa.text("resolved = false"))
    # Index for backlink queries: what references point to this work?
    op.create_index("ix_reference_target_work_id", "reference", ["target_work_id"])


def downgrade() -> None:
    op.drop_index("ix_reference_target_work_id", "reference")
    op.drop_index("ix_reference_unresolved", "reference")
    op.drop_column("reference", "resolved")
    op.drop_column("reference", "raw_text")
