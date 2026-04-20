from open_legis.model.db import make_engine


def test_make_engine_returns_working_engine(pg_url):
    eng = make_engine(pg_url)
    with eng.connect() as c:
        result = c.exec_driver_sql("SELECT 1").scalar()
        assert result == 1
    eng.dispose()
