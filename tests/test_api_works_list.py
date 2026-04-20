from fastapi.testclient import TestClient


def test_works_list_returns_loaded_fixtures(client: TestClient):
    r = client.get("/works")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] >= 1
    assert {"uri", "title", "type", "dv_ref"} <= set(d["items"][0].keys())


def test_works_filter_by_type(client: TestClient):
    r = client.get("/works?type=zakon")
    assert r.status_code == 200
    d = r.json()
    assert all(item["type"] == "zakon" for item in d["items"])


def test_works_pagination(client: TestClient):
    r = client.get("/works?page=1&page_size=1")
    assert r.status_code == 200
    d = r.json()
    assert d["page"] == 1
    assert d["page_size"] == 1
    assert len(d["items"]) <= 1
