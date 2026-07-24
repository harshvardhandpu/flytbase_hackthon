from app.config import Settings, normalize_database_url


def test_normalize_database_url_uses_psycopg_v3_for_railway_url() -> None:
    assert (
        normalize_database_url("postgresql://user:password@host:5432/database")
        == "postgresql+psycopg://user:password@host:5432/database"
    )


def test_normalize_database_url_preserves_explicit_driver() -> None:
    url = "postgresql+psycopg://user:password@host:5432/database"
    assert normalize_database_url(url) == url


def test_settings_normalizes_database_url() -> None:
    settings = Settings(database_url="postgresql://user:password@host:5432/database")
    assert settings.database_url == "postgresql+psycopg://user:password@host:5432/database"
