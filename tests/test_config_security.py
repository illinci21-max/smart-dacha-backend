import pytest
from pydantic import ValidationError

from app.config import Settings


def make_settings(**overrides) -> Settings:
    defaults = {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "DATABASE_SYNC_URL": "postgresql+psycopg2://user:pass@localhost:5432/db",
        "SECRET_KEY": "short-dev-key",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_cors_origins_parses_comma_separated_string():
    settings = make_settings(
        CORS_ORIGINS="https://app.example.com,https://admin.example.com"
    )

    assert settings.cors_origins_list == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_cors_origins_handles_empty_and_whitespace():
    settings = make_settings(
        CORS_ORIGINS=" https://app.example.com, ,https://admin.example.com, "
    )

    assert settings.cors_origins_list == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_secret_key_rejects_short_in_production():
    with pytest.raises(ValidationError, match="Minimum 64"):
        make_settings(ENVIRONMENT="production", SECRET_KEY="Aa1!")


def test_secret_key_rejects_common_values():
    for value in ("secret", "changeme", "dev", "test"):
        with pytest.raises(ValidationError, match="common insecure value"):
            make_settings(SECRET_KEY=value)


def test_secret_key_allows_short_in_development():
    settings = make_settings(ENVIRONMENT="development", SECRET_KEY="short-dev-key")

    assert settings.SECRET_KEY == "short-dev-key"


def test_is_production_returns_true_only_for_production_env():
    assert make_settings(ENVIRONMENT="production", SECRET_KEY="Aa1!" * 16).is_production
    assert not make_settings(ENVIRONMENT="staging").is_production
    assert not make_settings(ENVIRONMENT="development").is_production
