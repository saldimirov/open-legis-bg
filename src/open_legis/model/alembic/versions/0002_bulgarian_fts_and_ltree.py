"""bulgarian FTS and ltree

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-20

NOTE: postgres:16-alpine lacks the Bulgarian snowball dictionary, so the
tsvector uses the 'simple' config instead of 'bulgarian'. Full Bulgarian
stemming can be added later by installing the appropriate extension.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")

    op.execute("ALTER TABLE element ADD COLUMN path ltree")
    op.execute("CREATE INDEX element_path_gist_idx ON element USING GIST (path)")

    op.execute(
        """
        ALTER TABLE element
        ADD COLUMN tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector(
                'simple',
                coalesce(num, '') || ' ' || coalesce(heading, '') || ' ' || coalesce(text, '')
            )
        ) STORED
        """
    )
    op.execute("CREATE INDEX element_tsv_gin_idx ON element USING GIN (tsv)")

    op.execute("CREATE INDEX element_expr_parent_idx ON element (expression_id, parent_e_id)")
    op.execute("CREATE INDEX expression_work_date_idx ON expression (work_id, expression_date DESC)")
    op.execute("CREATE INDEX expression_is_latest_idx ON expression (work_id) WHERE is_latest")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS expression_is_latest_idx")
    op.execute("DROP INDEX IF EXISTS expression_work_date_idx")
    op.execute("DROP INDEX IF EXISTS element_expr_parent_idx")
    op.execute("DROP INDEX IF EXISTS element_tsv_gin_idx")
    op.execute("ALTER TABLE element DROP COLUMN tsv")
    op.execute("DROP INDEX IF EXISTS element_path_gist_idx")
    op.execute("ALTER TABLE element DROP COLUMN path")
    op.execute("DROP EXTENSION IF EXISTS ltree")
