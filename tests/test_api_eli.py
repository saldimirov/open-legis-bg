def test_get_work(client):
    r = client.get("/eli/bg/zakon/2000/test")
    assert r.status_code == 200
    d = r.json()
    assert d["uri"] == "/eli/bg/zakon/2000/test"
    assert d["work"]["type"] == "zakon"


def test_get_latest_expression(client):
    r = client.get("/eli/bg/zakon/2000/test/latest/bul")
    assert r.status_code == 200
    d = r.json()
    assert d["expression"]["date"] == "2000-01-01"
    assert d["expression"]["is_latest"] is True


def test_get_dated_expression(client):
    r = client.get("/eli/bg/zakon/2000/test/2000-01-01/bul")
    assert r.status_code == 200


def test_get_element(client):
    r = client.get("/eli/bg/zakon/2000/test/2000-01-01/bul/art_1")
    assert r.status_code == 200
    d = r.json()
    assert d["element"]["e_id"] == "art_1"
    assert len(d["element"]["children"]) == 2


def test_get_nested_element(client):
    r = client.get("/eli/bg/zakon/2000/test/2000-01-01/bul/art_1/para_1")
    assert r.status_code == 200
    d = r.json()
    assert d["element"]["e_id"] == "art_1__para_1"


def test_missing_work_is_404(client):
    r = client.get("/eli/bg/zakon/2000/nope")
    assert r.status_code == 404


def test_bad_eli_is_400(client):
    r = client.get("/eli/bg/zakon/abc/test")
    assert r.status_code in (400, 404)
