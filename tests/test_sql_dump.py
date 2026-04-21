import shutil

import pytest


@pytest.mark.skipif(not shutil.which("pg_dump"), reason="pg_dump not on PATH")
def test_sql_dump_runs_and_writes_gzipped_file(tmp_path, pg_url, monkeypatch):
    import gzip
    from pathlib import Path

    from open_legis.dumps.build import build_sql_dump
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

    out = tmp_path / "dump.sql.gz"
    build_sql_dump(database_url=pg_url, out_path=out)
    assert out.exists()
    body = gzip.decompress(out.read_bytes())
    assert b"CREATE TABLE" in body
    assert b"work" in body.lower()
