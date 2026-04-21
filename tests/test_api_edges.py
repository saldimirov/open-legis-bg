def test_amendments_inbound(client):
    r = client.get("/works/test/amendments?direction=in")
    assert r.status_code == 200
    assert "items" in r.json()


def test_references_outbound(client):
    r = client.get("/works/test/references?direction=out")
    assert r.status_code == 200
    assert "items" in r.json()


def test_works_missing_returns_404(client):
    r = client.get("/works/nonexistent/amendments")
    assert r.status_code == 404
