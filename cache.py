"""Redis cache for redirects (cache-aside).

Hot redirects are served straight from Redis so the database is only hit on a
cache miss. Cache entries never outlive the link's own expiry.
"""
from datetime import datetime, timezone

import redis

from app.config import get_settings

PREFIX = "link:"


def make_redis(url: str | None = None) -> redis.Redis:
    return redis.Redis.from_url(url or get_settings().redis_url, decode_responses=True)


class RedirectCache:
    def __init__(self, client: redis.Redis):
        self.r = client

    def get(self, code: str) -> str | None:
        try:
            return self.r.get(PREFIX + code)
        except redis.RedisError:
            return None  # cache is an optimisation; fail open to the DB

    def set(self, code: str, url: str, expires_at: datetime | None) -> None:
        ttl = get_settings().cache_ttl_seconds
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
            if remaining <= 0:
                return
            ttl = min(ttl, remaining)
        try:
            self.r.set(PREFIX + code, url, ex=ttl)
        except redis.RedisError:
            pass

    def delete(self, code: str) -> None:
        try:
            self.r.delete(PREFIX + code)
        except redis.RedisError:
            pass
