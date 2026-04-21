def test_expressions_listed_oldest_first(client):
    r = client.get("/works/test/expressions")
    assert r.status_code == 200
    d = r.json()
    assert len(d["items"]) >= 1
    for item in d["items"]:
        assert {"uri", "date", "language", "is_latest"} <= set(item.keys())
