def test_search_returns_results(client):
    # "алинея" appears in the minimal fixture text
    r = client.get("/search?q=алинея")
    assert r.status_code == 200
    d = r.json()
    assert "items" in d
    assert "total" in d
    assert d["page"] == 1


def test_search_empty_query_returns_422(client):
    r = client.get("/search?q=")
    assert r.status_code == 422


def test_search_with_type_filter(client):
    # "разпоредба" is in the fixture; filter by zakon (the fixture is a zakon)
    r = client.get("/search?q=разпоредба&type=zakon")
    assert r.status_code == 200


def test_search_pagination(client):
    r = client.get("/search?q=алинея&page=1&page_size=5")
    assert r.status_code == 200
    d = r.json()
    assert d["page_size"] == 5


def test_search_no_results_still_200(client):
    # A query that won't match anything — still returns 200 with empty list
    r = client.get("/search?q=nonexistentword12345xyz")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 0
    assert d["items"] == []
