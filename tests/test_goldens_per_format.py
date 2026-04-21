import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

GOLDEN = Path("tests/golden")


@pytest.fixture(scope="module")
def real_client(pg_url):
    from open_legis.api.app import create_app
    from open_legis.loader.cli import load_directory
    from open_legis.model import schema as m
    from open_legis.model.db import make_engine

    os.environ["DATABASE_URL"] = pg_url
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
    yield TestClient(create_app())
    eng.dispose()


def _check_or_write(path: Path, actual: bytes) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(actual)
        pytest.fail(f"Created new golden {path}; re-run to verify")
    expected = path.read_bytes()
    assert actual == expected, f"Golden drift at {path}. Re-create if intentional."


def test_zzd_2024_art1_json(real_client):
    r = real_client.get("/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_1")
    assert r.status_code == 200
    _check_or_write(GOLDEN / "zzd_2024_art1.json", r.content)


def test_zzd_2024_art1_akn(real_client):
    r = real_client.get(
        "/eli/bg/zakon/1950/zzd/2024-01-01/bul/art_1",
        headers={"Accept": "application/akn+xml"},
    )
    assert r.status_code == 200
    _check_or_write(GOLDEN / "zzd_2024_art1.akn.xml", r.content)


def test_zzd_work_ttl(real_client):
    r = real_client.get(
        "/eli/bg/zakon/1950/zzd",
        headers={"Accept": "text/turtle"},
    )
    assert r.status_code == 200
    _check_or_write(GOLDEN / "zzd_2024_art1.ttl", r.content)
