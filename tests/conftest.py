from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        yield pg.get_connection_url()


@pytest.fixture
def engine(pg_url):
    eng = create_engine(pg_url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    Sess = sessionmaker(bind=engine, expire_on_commit=False)
    with Sess() as s:
        yield s


from pathlib import Path as _Path

import pytest as _pytest
from fastapi.testclient import TestClient

from open_legis.api.app import create_app as _create_app
from open_legis.loader.cli import load_directory as _load_directory
from open_legis.model import schema as _m
from open_legis.model.db import make_engine as _make_engine


@_pytest.fixture
def client(pg_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    eng = _make_engine(pg_url)
    _m.Base.metadata.drop_all(eng)
    _m.Base.metadata.create_all(eng)
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
        _Path("tests/data/minimal_act.xml").read_text()
    )
    _load_directory(tmp_path / "fixtures" / "akn", engine=eng)
    app = _create_app()
    yield TestClient(app)
    eng.dispose()
