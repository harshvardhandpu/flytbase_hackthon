import os
import subprocess
import sys
from pathlib import Path

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


def test_tavily_api_key_strips_whitespace_and_quotes() -> None:
    """Railway UI pastes often include quotes or trailing newlines."""
    settings = Settings(tavily_api_key='  "tvly-test-key"  \n')
    assert settings.tavily_api_key == "tvly-test-key"


def test_tavily_api_key_empty_becomes_none() -> None:
    settings = Settings(tavily_api_key="   ")
    assert settings.tavily_api_key is None


def test_alembic_accepts_railway_database_url_without_psycopg2() -> None:
    environment = os.environ | {
        "DATABASE_URL": "postgresql://user:password@host:5432/database",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "psycopg2" not in result.stderr
    assert "CREATE TABLE alembic_version" in result.stdout
