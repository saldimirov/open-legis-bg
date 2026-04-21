def test_cache_control_on_resource(client):
    r = client.get("/eli/bg/zakon/2000/test")
    assert r.status_code == 200
    assert "max-age" in r.headers.get("cache-control", "")


def test_cors_allows_any_origin(client):
    r = client.get("/eli/bg/zakon/2000/test", headers={"Origin": "https://example.com"})
    assert r.headers.get("access-control-allow-origin") == "*"
