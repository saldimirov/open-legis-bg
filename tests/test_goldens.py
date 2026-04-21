import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine

GOLDEN = Path("tests/golden/works.json")


def test_works_golden(pg_url):
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    load_directory(Path("fixtures/akn"), engine=eng)
    with Session(eng) as s:
        rows = [
            {
                "eli_uri": w.eli_uri,
                "act_type": w.act_type.value,
                "title": w.title,
                "dv": [w.dv_broy, w.dv_year],
                "expressions": sorted(
                    e.expression_date.isoformat() for e in w.expressions
                ),
            }
            for w in sorted(
                s.scalars(select(m.Work)).all(), key=lambda x: x.eli_uri
            )
        ]
    expected = json.loads(GOLDEN.read_text())
    assert rows == expected, (
        "Work set drifted from golden. If intentional, update "
        "tests/golden/works.json."
    )
