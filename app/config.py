"""
App Configuration — all settings via pydantic-settings.

FIXES from Code Review:
  §1.2  — Added REDIS_POOL_SIZE for unified connection pooling
  §2.2  — Stronger SECRET_KEY validation; never allow default in production
  §4.4  — Added WEB_CONCURRENCY for dynamic Gunicorn workers
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationInfo, field_validator
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "Розумний Дачник"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "https://app.smartdacha.ua"
    ADMIN_EMAILS: str = ""
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15        # §2.3: short-lived (was 1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://smartdacha:smartdacha@localhost:5432/smartdacha"
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://smartdacha:smartdacha@localhost:5432/smartdacha"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_POOL_SIZE: int = 20                    # §1.2: shared pool size
    REDIS_WEATHER_DB: int = 2
    REDIS_CACHE_DB: int = 3

    # ── Storage S3-compatible ─────────────────────────────────────────────────
    S3_BUCKET: str = "smartdacha-media"
    S3_REGION: str = "eu-central-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_ENDPOINT_URL: str | None = None
    CDN_BASE_URL: str | None = None

    # ── External APIs ─────────────────────────────────────────────────────────
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1"
    GOOGLE_VISION_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_DAILY_BUDGET: int = 100
    GEMINI_PROFILE_LOOKUP_RATE_LIMIT: str = "30/minute"
    GEMINI_PROFILE_LOOKUPS_PER_GARDEN_REQUEST: int = 5
    PLANTNET_API_KEY: str = ""

    # ── Firebase ─────────────────────────────────────────────────────────────
    FIREBASE_CREDENTIALS_PATH: str = "firebase-credentials.json"

    # ── Stripe ───────────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PREMIUM_PRICE_ID: str = ""
    STRIPE_PREMIUM_PLUS_PRICE_ID: str = ""

    # ── SaaS Limits ───────────────────────────────────────────────────────────
    FREE_PLOTS_LIMIT: int = 999
    FREE_PLANTS_LIMIT: int = 9999
    FREE_DIAGNOSES_PER_WEEK: int = 3
    FREE_DIAGNOSES_PER_MONTH: int = 12
    FREE_PHOTOS_PER_ENTRY: int = 100

    # ── Weather cache ─────────────────────────────────────────────────────────
    WEATHER_CACHE_TTL_SECONDS: int = 6 * 3600
    WEATHER_GRID_PRECISION: int = 1
    GARDEN_ACTION_RETENTION_DAYS: int = 90

    # Observability
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.05
    RELEASE_VERSION: str = "dev"
    PROMETHEUS_METRICS_ENABLED: bool = True
    LOG_FORMAT: Literal["json", "text"] = "text"

    # ── Deployment ────────────────────────────────────────────────────────────
    WEB_CONCURRENCY: int = 2                     # §4.4: Gunicorn workers

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL is required")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development")
        value = (v or "").strip()
        if value.lower() in {"secret", "changeme", "dev", "test"}:
            raise ValueError("SECRET_KEY uses a common insecure value")
        if env == "production":
            if len(value) < 64:
                raise ValueError(
                    f"SECRET_KEY too short ({len(value)} chars). Minimum 64 for production."
                )
            categories = [
                any(ch.islower() for ch in value),
                any(ch.isupper() for ch in value),
                any(ch.isdigit() for ch in value),
                any(not ch.isalnum() for ch in value),
            ]
            if sum(categories) < 4:
                raise ValueError(
                    "SECRET_KEY must contain lowercase, uppercase, digit, and symbol in production"
                )
        return v

    def get_cdn_base_url(self) -> str:
        if self.CDN_BASE_URL:
            return self.CDN_BASE_URL
        if self.S3_ENDPOINT_URL:
            return f"{self.S3_ENDPOINT_URL}/{self.S3_BUCKET}"
        return f"https://{self.S3_BUCKET}.s3.{self.S3_REGION}.amazonaws.com"

    @property
    def admin_email_set(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.ADMIN_EMAILS.split(",")
            if email.strip()
        }

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
