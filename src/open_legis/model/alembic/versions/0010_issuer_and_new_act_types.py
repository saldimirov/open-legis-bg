"""Add issuer enum + column; expand act_type with flat reshenie and 7 new types.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_NEW_ACT_TYPES = [
    "reshenie",
    "instruktsiya",
    "tarifa",
    "zapoved",
    "deklaratsiya",
    "opredelenie",
    "dogovor",
    "saobshtenie",
]

_ISSUER_VALUES = [
    "ns", "ms", "president", "ministry", "commission",
    "agency", "court", "ks", "vas", "vss", "bnb", "municipality", "other",
]

_RESHENIE_ISSUER_MAP = {
    "reshenie_ks":   "ks",
    "reshenie_ns":   "ns",
    "reshenie_ms":   "ms",
    "reshenie_kevr": "commission",
    "reshenie_kfn":  "commission",
    "reshenie_nhif": "commission",
}

_FIXED_ISSUERS = {
    "zakon":        "ns",
    "zid":          "ns",
    "byudjet":      "ns",
    "kodeks":       "ns",
    "ratifikatsiya": "ns",
    "konstitutsiya": "ns",
    "ukaz":         "president",
    "postanovlenie": "ms",
}


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Extend act_type enum with new values
    for val in _NEW_ACT_TYPES:
        conn.execute(sa.text(f"ALTER TYPE act_type ADD VALUE IF NOT EXISTS '{val}'"))

    # 2. Create issuer enum type
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'issuer') THEN "
        "    CREATE TYPE issuer AS ENUM (" +
        ", ".join(f"'{v}'" for v in _ISSUER_VALUES) +
        "  ); END IF; END $$"
    ))

    # 3. Add issuer column (nullable)
    op.add_column("work", sa.Column("issuer", sa.Enum(*_ISSUER_VALUES, name="issuer"), nullable=True))

    # 4. Migrate reshenie_* → reshenie + issuer
    for old_type, issuer_val in _RESHENIE_ISSUER_MAP.items():
        conn.execute(sa.text(
            f"UPDATE work SET act_type = 'reshenie', issuer = '{issuer_val}' "
            f"WHERE act_type = '{old_type}'"
        ))

    # 5. Back-fill issuer for deterministic act types
    for act_type_val, issuer_val in _FIXED_ISSUERS.items():
        conn.execute(sa.text(
            f"UPDATE work SET issuer = '{issuer_val}' "
            f"WHERE act_type = '{act_type_val}' AND issuer IS NULL"
        ))


def downgrade() -> None:
    op.drop_column("work", "issuer")
    op.execute("DROP TYPE IF EXISTS issuer")
