"""Environment-based configuration.

All settings come from environment variables (or a local .env file), so the
same image can run unchanged in dev, CI and production.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Infrastructure
    database_url: str = "postgresql+psycopg2://shortener:shortener@localhost:5432/shortener"
    redis_url: str = "redis://localhost:6379/0"

    # Public base URL used when building short links in responses
    base_url: str = "http://localhost:8000"

    # Short code generation
    code_length: int = 7
    max_code_retries: int = 5

    # Expiration policy
    default_ttl_seconds: int | None = None  # None = links never expire by default
    max_ttl_seconds: int = 60 * 60 * 24 * 365  # hard cap: 1 year

    # Caching
    cache_ttl_seconds: int = 60 * 60  # upper bound for a cached redirect

    # Rate limiting (fixed window, per client IP, on link creation)
    rate_limit_requests: int = 20
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
