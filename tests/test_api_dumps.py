def test_dumps_latest_served_when_present(tmp_path, monkeypatch):
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    (dumps / "latest.tar.gz").write_bytes(b"\x1f\x8b\x08\x00fake")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
    monkeypatch.setenv("OPEN_LEGIS_DUMPS_DIR", str(dumps))

    from fastapi.testclient import TestClient
    from open_legis.api.app import create_app

    local = TestClient(create_app())
    r = local.get("/dumps/latest.tar.gz")
    assert r.status_code == 200
    assert r.content.startswith(b"\x1f\x8b")


def test_dumps_listing(tmp_path, monkeypatch):
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    (dumps / "latest.tar.gz").write_bytes(b"x")
    (dumps / "2026-04-20.tar.gz").write_bytes(b"x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
    monkeypatch.setenv("OPEN_LEGIS_DUMPS_DIR", str(dumps))

    from fastapi.testclient import TestClient
    from open_legis.api.app import create_app

    local = TestClient(create_app())
    r = local.get("/dumps/")
    assert r.status_code == 200
    d = r.json()
    assert "latest.tar.gz" in [i["name"] for i in d["items"]]


def test_dumps_missing_returns_404(tmp_path, monkeypatch):
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
    monkeypatch.setenv("OPEN_LEGIS_DUMPS_DIR", str(dumps))

    from fastapi.testclient import TestClient
    from open_legis.api.app import create_app

    local = TestClient(create_app())
    r = local.get("/dumps/nonexistent.tar.gz")
    assert r.status_code == 404
