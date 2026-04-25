"""add consolidation_op table for parsed ZID amendment operations

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-22
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TYPE consolidation_op_type AS ENUM (
            'ELEMENT_SUBSTITUTION', 'ELEMENT_INSERTION', 'ELEMENT_REPEAL',
            'TEXT_SUBSTITUTION', 'TEXT_INSERTION', 'TEXT_DELETION'
        )
    """)
    op.execute("""
        CREATE TYPE consolidation_op_status AS ENUM (
            'PARSED', 'RESOLVED', 'APPLIED', 'FAILED'
        )
    """)
    op.execute("""
        CREATE TABLE consolidation_op (
            id          UUID PRIMARY KEY,
            amendment_id UUID NOT NULL REFERENCES amendment(id) ON DELETE CASCADE,
            source_e_id TEXT NOT NULL,
            sequence    INTEGER NOT NULL DEFAULT 0,
            target_ref_raw TEXT NOT NULL,
            target_e_id TEXT,
            op_type     consolidation_op_type NOT NULL,
            old_text    TEXT,
            new_text    TEXT,
            status      consolidation_op_status NOT NULL DEFAULT 'PARSED',
            error       TEXT
        )
    """)
    op.execute("CREATE INDEX ix_consolidation_op_amendment_id ON consolidation_op (amendment_id)")
    op.execute("CREATE INDEX ix_consolidation_op_status ON consolidation_op (status)")


def downgrade() -> None:
    op.drop_table("consolidation_op")
    op.execute("DROP TYPE IF EXISTS consolidation_op_type")
    op.execute("DROP TYPE IF EXISTS consolidation_op_status")
