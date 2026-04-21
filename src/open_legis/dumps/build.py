import gzip
import io
import json
import tarfile
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from open_legis.model import schema as m

EPOCH = 1577836800  # 2020-01-01 00:00:00 UTC — fixed for determinism


def build_tarball(engine: Engine, fixtures_dir: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_buf = io.BytesIO()
    with tarfile.open(fileobj=raw_buf, mode="w") as tf:
        _add_fixtures(tf, fixtures_dir)
        _add_db_snapshot(tf, engine)

    raw_bytes = raw_buf.getvalue()
    with open(out_path, "wb") as fh:
        gz = gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0)
        try:
            gz.write(raw_bytes)
        finally:
            gz.close()


def _add_file(tf: tarfile.TarFile, arcname: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mtime = EPOCH
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o644
    tf.addfile(info, io.BytesIO(data))


def _add_fixtures(tf: tarfile.TarFile, fixtures_dir: Path) -> None:
    for f in sorted(fixtures_dir.rglob("*")):
        if f.is_dir():
            continue
        arcname = "fixtures/" + str(f.relative_to(fixtures_dir.parent)).replace("\\", "/")
        _add_file(tf, arcname, f.read_bytes())


def _add_db_snapshot(tf: tarfile.TarFile, engine: Engine) -> None:
    with Session(engine) as s:
        works = sorted(s.scalars(select(m.Work)).all(), key=lambda w: w.eli_uri)
        payload = {
            "works": [
                {
                    "uri": w.eli_uri,
                    "type": w.act_type.value,
                    "title": w.title,
                    "title_short": w.title_short,
                    "dv": {"broy": w.dv_broy, "year": w.dv_year, "position": w.dv_position},
                    "adoption_date": w.adoption_date.isoformat() if w.adoption_date else None,
                    "status": w.status.value,
                    "expressions": sorted(
                        [
                            {
                                "date": e.expression_date.isoformat(),
                                "language": e.language,
                                "is_latest": e.is_latest,
                                "source_file": e.source_file,
                            }
                            for e in w.expressions
                        ],
                        key=lambda x: (x["date"], x["language"]),
                    ),
                    "external_ids": sorted(
                        [{"source": x.source.value, "value": x.external_value} for x in w.external_ids],
                        key=lambda x: x["source"],
                    ),
                }
                for w in works
            ]
        }
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    _add_file(tf, "data/works.json", body)


import gzip as _gzip
import subprocess
from urllib.parse import urlparse


def build_sql_dump(database_url: str, out_path: Path) -> None:
    """Run pg_dump and gzip its output into out_path."""
    parsed = urlparse(database_url.replace("+psycopg", ""))
    env = {
        "PGHOST": parsed.hostname or "localhost",
        "PGPORT": str(parsed.port or 5432),
        "PGUSER": parsed.username or "",
        "PGPASSWORD": parsed.password or "",
        "PGDATABASE": parsed.path.lstrip("/") or "",
    }
    cmd = [
        "pg_dump",
        "-Fp",
        "--no-owner",
        "--no-acl",
        "--no-comments",
        env["PGDATABASE"],
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import os
    result = subprocess.run(
        cmd,
        env=env | {"PATH": os.environ.get("PATH", "")},
        capture_output=True,
        check=True,
    )
    with open(out_path, "wb") as fh:
        gz = _gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0)
        try:
            gz.write(result.stdout)
        finally:
            gz.close()
