import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_legis.api.renderers.json_render import render_work, render_expression, render_element
from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine


@pytest.fixture
def loaded(pg_url, tmp_path):
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
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )
    load_directory(tmp_path / "fixtures" / "akn", engine=eng)
    yield eng
    eng.dispose()


def test_render_work(loaded):
    with Session(loaded) as s:
        work = s.scalars(select(m.Work)).one()
        out = render_work(work)
        d = out.model_dump(mode="json", by_alias=True)
        assert d["uri"] == "/eli/bg/zakon/2000/test"
        assert d["work"]["type"] == "zakon"
        assert d["_links"]["self"] == "/eli/bg/zakon/2000/test"


def test_render_expression_includes_toc(loaded):
    with Session(loaded) as s:
        expr = s.scalars(select(m.Expression)).one()
        out = render_expression(expr)
        d = out.model_dump(mode="json", by_alias=True)
        assert d["expression"]["date"] == "2000-01-01"
        assert d["element"]["children"][0]["e_id"] == "art_1"


def test_render_element_subtree(loaded):
    with Session(loaded) as s:
        expr = s.scalars(select(m.Expression)).one()
        art1 = s.scalars(
            select(m.Element).where(
                m.Element.expression_id == expr.id, m.Element.e_id == "art_1"
            )
        ).one()
        out = render_element(expr, art1)
        d = out.model_dump(mode="json", by_alias=True)
        assert d["element"]["e_id"] == "art_1"
        assert len(d["element"]["children"]) == 2  # two paragraphs
