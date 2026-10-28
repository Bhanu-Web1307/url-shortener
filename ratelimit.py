"""Fixed-window rate limiter backed by Redis (INCR + EXPIRE).

Each client IP gets `rate_limit_requests` calls per `rate_limit_window_seconds`.
The counter key expires automatically, so no cleanup job is needed.
"""
import redis
from fastapi import HTTPException, Request

from app.config import get_settings


class RateLimiter:
    def __init__(self, client: redis.Redis):
        self.r = client

    def check(self, identity: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        s = get_settings()
        key = f"rl:{identity}"
        try:
            pipe = self.r.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()
            if ttl is None or ttl < 0:
                self.r.expire(key, s.rate_limit_window_seconds)
                ttl = s.rate_limit_window_seconds
        except redis.RedisError:
            return True, 0  # fail open: don't take the service down with Redis
        if count > s.rate_limit_requests:
            return False, max(ttl, 1)
        return True, 0


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(limiter: RateLimiter, request: Request) -> None:
    allowed, retry_after = limiter.check(client_ip(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
