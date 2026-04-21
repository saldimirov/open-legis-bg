def test_by_dv_redirects_to_eli(client):
    # conftest fixture: act_type=zakon, year=2000, slug=test, dv_broy=1, dv_year=2000, dv_position=1
    r = client.get("/by-dv/2000/1/1", follow_redirects=False)
    assert r.status_code == 301
    assert "/eli/bg/zakon/2000/test" in r.headers["location"]


def test_by_dv_unknown_is_404(client):
    r = client.get("/by-dv/1900/1/1", follow_redirects=False)
    assert r.status_code == 404
