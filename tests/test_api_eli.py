from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_legis.api.app import create_app
from open_legis.loader.cli import load_directory
from open_legis.model import schema as m
from open_legis.model.db import make_engine


@pytest.fixture
def client(pg_url, tmp_path, monkeypatch):
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
    dest = tmp_path / "fixtures" / "akn" / "zakon" / "2000" / "test" / "expressions"
    dest.mkdir(parents=True)
    (dest / "2000-01-01.bul.xml").write_text(
        Path("tests/data/minimal_act.xml").read_text()
    )
    load_directory(tmp_path / "fixtures" / "akn", engine=eng)
    app = create_app()
    yield TestClient(app)
    eng.dispose()


def test_get_work(client):
    r = client.get("/eli/bg/zakon/2000/test")
    assert r.status_code == 200
    d = r.json()
    assert d["uri"] == "/eli/bg/zakon/2000/test"
    assert d["work"]["type"] == "zakon"


def test_get_latest_expression(client):
    r = client.get("/eli/bg/zakon/2000/test/latest/bul")
    assert r.status_code == 200
    d = r.json()
    assert d["expression"]["date"] == "2000-01-01"
    assert d["expression"]["is_latest"] is True


def test_get_dated_expression(client):
    r = client.get("/eli/bg/zakon/2000/test/2000-01-01/bul")
    assert r.status_code == 200


def test_get_element(client):
    r = client.get("/eli/bg/zakon/2000/test/2000-01-01/bul/art_1")
    assert r.status_code == 200
    d = r.json()
    assert d["element"]["e_id"] == "art_1"
    assert len(d["element"]["children"]) == 2


def test_get_nested_element(client):
    r = client.get("/eli/bg/zakon/2000/test/2000-01-01/bul/art_1/para_1")
    assert r.status_code == 200
    d = r.json()
    assert d["element"]["e_id"] == "art_1__para_1"


def test_missing_work_is_404(client):
    r = client.get("/eli/bg/zakon/2000/nope")
    assert r.status_code == 404


def test_bad_eli_is_400(client):
    r = client.get("/eli/bg/zakon/abc/test")
    assert r.status_code in (400, 404)
