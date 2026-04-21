from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_legis.api.app import create_app
from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine


@pytest.fixture
def pit_client(pg_url, tmp_path, monkeypatch):
    """Load two expressions of the same act at different dates."""
    monkeypatch.setenv("DATABASE_URL", pg_url)
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

    base_xml = Path("tests/data/minimal_act.xml").read_text()
    expr_dir = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    expr_dir.mkdir(parents=True)

    # v1: "wording ONE"
    v1 = base_xml.replace("Това е първа алинея.", "Wording ONE (as of 2000-01-01).")
    (expr_dir / "2000-01-01.bul.xml").write_text(v1)

    # v2: "wording TWO" at a later expression date
    v2 = base_xml.replace("Това е първа алинея.", "Wording TWO (as of 2005-01-01).")
    v2 = v2.replace('date="2000-01-01"', 'date="2005-01-01"')
    v2 = v2.replace("bul@2000-01-01", "bul@2005-01-01")
    (expr_dir / "2005-01-01.bul.xml").write_text(v2)

    load_directory(tmp_path / "fixtures" / "akn", engine=eng)
    yield TestClient(create_app())
    eng.dispose()


def test_point_in_time_returns_different_text(pit_client):
    r1 = pit_client.get("/eli/bg/zakon/2000/test/2000-01-01/bul/art_1/para_1")
    r2 = pit_client.get("/eli/bg/zakon/2000/test/2005-01-01/bul/art_1/para_1")
    assert r1.status_code == 200
    assert r2.status_code == 200
    t1 = r1.json()["element"]["text"] or ""
    t2 = r2.json()["element"]["text"] or ""
    assert "ONE" in t1
    assert "TWO" in t2
    assert t1 != t2


def test_latest_resolves_to_most_recent(pit_client):
    r = pit_client.get("/eli/bg/zakon/2000/test/latest/bul/art_1/para_1")
    assert r.status_code == 200
    assert "TWO" in (r.json()["element"]["text"] or "")


def test_midpoint_date_resolves_to_earlier_expression(pit_client):
    # Date between the two expressions resolves to the greatest <= request date.
    r = pit_client.get("/eli/bg/zakon/2000/test/2002-06-15/bul/art_1/para_1")
    assert r.status_code == 200
    assert "ONE" in (r.json()["element"]["text"] or "")
