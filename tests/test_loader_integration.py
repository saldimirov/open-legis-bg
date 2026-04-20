from pathlib import Path

import pytest
from sqlalchemy import select

from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine


@pytest.fixture
def fresh_db(pg_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = make_engine(pg_url)
    m.Base.metadata.drop_all(eng)
    m.Base.metadata.create_all(eng)
    # path column + tsv are normally added by migration 0002 — add by hand for this test
    with eng.begin() as c:
        c.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS ltree")
        c.exec_driver_sql("ALTER TABLE element ADD COLUMN IF NOT EXISTS path ltree")
        c.exec_driver_sql(
            "ALTER TABLE element ADD COLUMN IF NOT EXISTS tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(text,''))) STORED"
        )
    yield eng
    m.Base.metadata.drop_all(eng)
    eng.dispose()


def test_load_minimal_fixture(fresh_db, tmp_path):
    # stage fixture in a fixtures/akn/... layout
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    src = Path("tests/data/minimal_act.xml").read_text()
    (dest / "2000-01-01.bul.xml").write_text(src)

    load_directory(tmp_path / "fixtures" / "akn", engine=fresh_db)

    with fresh_db.connect() as c:
        from sqlalchemy.orm import Session
        with Session(fresh_db) as s:
            works = s.scalars(select(m.Work)).all()
            assert len(works) == 1
            assert works[0].eli_uri == "/eli/bg/zakon/2000/test"
            exprs = s.scalars(select(m.Expression)).all()
            assert len(exprs) == 1
            assert exprs[0].is_latest is True
            elems = s.scalars(select(m.Element)).all()
            assert len(elems) == 5


def test_load_is_idempotent(fresh_db, tmp_path):
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )

    load_directory(tmp_path / "fixtures" / "akn", engine=fresh_db)
    load_directory(tmp_path / "fixtures" / "akn", engine=fresh_db)

    from sqlalchemy.orm import Session
    with Session(fresh_db) as s:
        works = s.scalars(select(m.Work)).all()
        assert len(works) == 1
        elems = s.scalars(select(m.Element)).all()
        assert len(elems) == 5
