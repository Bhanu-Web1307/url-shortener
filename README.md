# URL Shortener Service

A scalable URL shortening service built with **FastAPI**, **PostgreSQL** and **Redis**, containerised with **Docker**.

## Features

- **REST API** to create, inspect, delete and resolve short links
- **Redis caching** (cache-aside): hot redirects are served without touching the database; cache entries never outlive a link's expiry
- **Rate limiting**: per-IP fixed-window limiter in Redis on link creation (returns `429` + `Retry-After`)
- **Collision-resistant short codes**: 7-char base62 codes from a CSPRNG (62^7 ≈ 3.5 trillion), backed by a database `UNIQUE` constraint with automatic retry on conflict
- **Expiration policies**: per-link `ttl_seconds`, optional global default, and a hard max TTL; expired links return `410 Gone`
- **Custom aliases** with validation and reserved-word protection (`409` on conflict)
- **Click analytics**: atomic SQL counter increments, safe under concurrent traffic
- **Environment-based configuration** (12-factor), non-root Docker image, health checks
- Fails open if Redis is down (redirects fall back to PostgreSQL)

## Architecture

```
Client ──► FastAPI ──► Redis  (redirect cache + rate-limit counters)
              │
              └──────► PostgreSQL (source of truth: links table)
```

Redirect flow: `GET /{code}` → Redis lookup → (miss) PostgreSQL lookup → populate cache → `307` redirect.

## Quick start (Docker)

```bash
cp .env.example .env        # edit POSTGRES_PASSWORD
docker compose up --build
```

API: http://localhost:8000 · Interactive docs: http://localhost:8000/docs

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/links` | Create a short link |
| `GET` | `/api/links/{code}` | Link metadata + click count |
| `DELETE` | `/api/links/{code}` | Delete a link (and its cache entry) |
| `GET` | `/{code}` | Redirect to the original URL |
| `GET` | `/health` | Liveness check |

### Example

```bash
curl -X POST http://localhost:8000/api/links \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/a/very/long/path", "ttl_seconds": 86400}'
```

```json
{
  "code": "aZ3kP9q",
  "short_url": "http://localhost:8000/aZ3kP9q",
  "original_url": "https://example.com/a/very/long/path",
  "created_at": "2026-10-27T17:30:00Z",
  "expires_at": "2026-10-28T17:30:00Z"
}
```

Optional body fields: `custom_alias` (3–32 chars of `A-Za-z0-9_-`), `ttl_seconds`.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | local Postgres | SQLAlchemy URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `BASE_URL` | `http://localhost:8000` | Prefix for returned short URLs |
| `CODE_LENGTH` | `7` | Generated code length |
| `DEFAULT_TTL_SECONDS` | unset | Default link lifetime (unset = never expires) |
| `MAX_TTL_SECONDS` | 1 year | Cap on any TTL |
| `CACHE_TTL_SECONDS` | `3600` | Max cache lifetime of a redirect |
| `RATE_LIMIT_REQUESTS` | `20` | Creates allowed per window per IP |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Window length |

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Tests use SQLite and `fakeredis`, so no external services are needed.

To run the API against local Postgres/Redis:

```bash
docker compose up db redis -d
export DATABASE_URL=postgresql+psycopg2://shortener:change-me@localhost:5432/shortener
uvicorn app.main:app --reload
```

## Project layout

```
app/
  main.py        routes + dependency wiring
  service.py     create/resolve logic, collision retry
  shortcode.py   base62 code generator
  cache.py       Redis redirect cache
  ratelimit.py   Redis rate limiter
  models.py      SQLAlchemy model
  schemas.py     Pydantic request/response models
  config.py      env-based settings
  db.py          engine + session
tests/           pytest suite
```

## Possible next steps

- Alembic migrations instead of `create_all`
- Async SQLAlchemy / asyncpg and redis.asyncio
- Buffered click counting (Redis counters flushed in batches) for very high read throughput
- Sliding-window or token-bucket rate limiting; API keys for per-user quotas
