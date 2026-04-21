import hashlib
import tarfile
from pathlib import Path

import pytest


@pytest.fixture
def built_tarball(pg_url, tmp_path, monkeypatch):
    from open_legis.dumps.build import build_tarball
    from open_legis.loader.cli import load_directory
    from open_legis.model import schema as m
    from open_legis.model.db import make_engine

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
    load_directory(Path("fixtures/akn"), engine=eng)
    out = tmp_path / "snapshot.tar.gz"
    build_tarball(engine=eng, fixtures_dir=Path("fixtures/akn"), out_path=out)
    return out


def test_tarball_contains_akn_and_json(built_tarball):
    with tarfile.open(built_tarball, "r:gz") as tf:
        names = tf.getnames()
    assert any(n.endswith(".bul.xml") for n in names)
    assert any(n.endswith("works.json") for n in names)


def test_tarball_is_deterministic(tmp_path, pg_url, monkeypatch):
    from open_legis.dumps.build import build_tarball
    from open_legis.loader.cli import load_directory
    from open_legis.model import schema as m
    from open_legis.model.db import make_engine

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
    load_directory(Path("fixtures/akn"), engine=eng)

    out1 = tmp_path / "a.tar.gz"
    out2 = tmp_path / "b.tar.gz"
    build_tarball(engine=eng, fixtures_dir=Path("fixtures/akn"), out_path=out1)
    build_tarball(engine=eng, fixtures_dir=Path("fixtures/akn"), out_path=out2)

    assert hashlib.sha256(out1.read_bytes()).hexdigest() == hashlib.sha256(
        out2.read_bytes()
    ).hexdigest()
