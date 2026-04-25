"""dv_item table

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dv_item",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dv_year", sa.Integer(), nullable=False),
        sa.Column("dv_broy", sa.Integer(), nullable=False),
        sa.Column("dv_position", sa.Integer(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("work_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["work_id"], ["work.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dv_year", "dv_broy", "dv_position"),
    )
    op.create_index("ix_dv_item_issue", "dv_item", ["dv_year", "dv_broy"])


def downgrade() -> None:
    op.drop_index("ix_dv_item_issue", "dv_item")
    op.drop_table("dv_item")
