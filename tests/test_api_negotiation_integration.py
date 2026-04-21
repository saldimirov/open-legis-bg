def test_akn_response_type(client):
    r = client.get(
        "/eli/bg/zakon/2000/test/2000-01-01/bul",
        headers={"Accept": "application/akn+xml"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/akn+xml")
    assert r.content.startswith(b"<")


def test_turtle_response_type(client):
    r = client.get(
        "/eli/bg/zakon/2000/test",
        headers={"Accept": "text/turtle"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/turtle")
    assert b"eli:" in r.content or b"<http://data.europa.eu/eli/ontology#" in r.content


def test_format_query_override_wins_over_accept(client):
    r = client.get(
        "/eli/bg/zakon/2000/test?format=ttl",
        headers={"Accept": "application/json"},
    )
    assert r.headers["content-type"].startswith("text/turtle")


def test_default_is_json(client):
    r = client.get("/eli/bg/zakon/2000/test")
    assert r.headers["content-type"].startswith("application/json")
