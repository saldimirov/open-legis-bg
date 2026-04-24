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

# Old migrations created uppercase enum labels; rename them to lowercase for consistency.
# RENAME VALUE is idempotent-safe via DO block (no IF EXISTS in PostgreSQL DDL).
_UPPERCASE_RENAMES = [
    ("KONSTITUTSIYA", "konstitutsiya"),
    ("KODEKS",        "kodeks"),
    ("ZAKON",         "zakon"),
    ("NAREDBA",       "naredba"),
    ("PRAVILNIK",     "pravilnik"),
    ("POSTANOVLENIE", "postanovlenie"),
    ("UKAZ",          "ukaz"),
    ("ZID",           "zid"),
    ("BYUDJET",       "byudjet"),
    ("RATIFIKATSIYA", "ratifikatsiya"),
    ("RAZPOREZHANE",  "razporezhane"),
    ("RESHENIE_KS",   "reshenie_ks"),
    ("RESHENIE_NS",   "reshenie_ns"),
    ("RESHENIE_MS",   "reshenie_ms"),
    ("RESHENIE_KEVR", "reshenie_kevr"),
    ("RESHENIE_KFN",  "reshenie_kfn"),
    ("RESHENIE_NHIF", "reshenie_nhif"),
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
    # Step 1: ADD new enum values — must be outside a transaction in PostgreSQL
    with op.get_context().autocommit_block():
        for val in _NEW_ACT_TYPES:
            op.execute(sa.text(f"ALTER TYPE act_type ADD VALUE IF NOT EXISTS '{val}'"))

    # Step 2: rename uppercase legacy labels → lowercase (RENAME VALUE is transactional)
    conn = op.get_bind()
    for old_label, new_label in _UPPERCASE_RENAMES:
        conn.execute(sa.text(
            f"DO $$ BEGIN "
            f"  IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid "
            f"             WHERE t.typname = 'act_type' AND e.enumlabel = '{old_label}') THEN "
            f"    ALTER TYPE act_type RENAME VALUE '{old_label}' TO '{new_label}'; "
            f"  END IF; "
            f"END $$"
        ))

    for type_name, renames in [
        ("act_status", [
            ("IN_FORCE",           "in_force"),
            ("REPEALED",           "repealed"),
            ("PARTIALLY_IN_FORCE", "partially_in_force"),
        ]),
        ("element_type", [
            ("PART",       "part"),
            ("TITLE",      "title"),
            ("CHAPTER",    "chapter"),
            ("SECTION",    "section"),
            ("ARTICLE",    "article"),
            ("PARAGRAPH",  "paragraph"),
            ("POINT",      "point"),
            ("LETTER",     "letter"),
            ("HCONTAINER", "hcontainer"),
        ]),
        ("amendment_op", [
            ("INSERTION",     "insertion"),
            ("SUBSTITUTION",  "substitution"),
            ("REPEAL",        "repeal"),
            ("RENUMBERING",   "renumbering"),
        ]),
        ("external_source", [
            ("LEX_BG",          "lex_bg"),
            ("PARLIAMENT_BG",   "parliament_bg"),
            ("DV_PARLIAMENT_BG","dv_parliament_bg"),
        ]),
        ("reference_type", [
            ("CITES",  "cites"),
            ("DEFINES","defines"),
        ]),
    ]:
        for old_label, new_label in renames:
            conn.execute(sa.text(
                f"DO $$ BEGIN "
                f"  IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid "
                f"             WHERE t.typname = '{type_name}' AND e.enumlabel = '{old_label}') THEN "
                f"    ALTER TYPE {type_name} RENAME VALUE '{old_label}' TO '{new_label}'; "
                f"  END IF; "
                f"END $$"
            ))

    # Step 3: everything else runs in the normal transaction (new values now committed)

    # Create issuer enum type
    conn.execute(sa.text(
        "DO $$ BEGIN "
        "  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'issuer') THEN "
        "    CREATE TYPE issuer AS ENUM (" +
        ", ".join(f"'{v}'" for v in _ISSUER_VALUES) +
        "  ); END IF; END $$"
    ))

    # Add issuer column (nullable)
    op.add_column("work", sa.Column("issuer", sa.Enum(*_ISSUER_VALUES, name="issuer"), nullable=True))

    # Migrate reshenie_* → reshenie + issuer
    # Use ::text cast on the column to bypass PostgreSQL enum label validation
    # (old migrations stored uppercase labels; new values are lowercase)
    for old_type, issuer_val in _RESHENIE_ISSUER_MAP.items():
        conn.execute(sa.text(
            f"UPDATE work SET act_type = 'reshenie', issuer = '{issuer_val}' "
            f"WHERE act_type::text ILIKE '{old_type}'"
        ))

    # Back-fill issuer for deterministic act types (no-op on fresh DB)
    for act_type_val, issuer_val in _FIXED_ISSUERS.items():
        conn.execute(sa.text(
            f"UPDATE work SET issuer = '{issuer_val}' "
            f"WHERE act_type::text ILIKE '{act_type_val}' AND issuer IS NULL"
        ))


def downgrade() -> None:
    op.drop_column("work", "issuer")
    op.execute("DROP TYPE IF EXISTS issuer")
