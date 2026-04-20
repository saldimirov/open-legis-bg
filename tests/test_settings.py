from open_legis.settings import Settings


def test_settings_reads_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@h:5432/d")
    s = Settings()
    assert s.database_url == "postgresql+psycopg://x:y@h:5432/d"


def test_settings_default_fixtures_dir():
    s = Settings(database_url="postgresql+psycopg://x:y@h:5432/d")
    assert str(s.fixtures_dir).endswith("fixtures/akn")
