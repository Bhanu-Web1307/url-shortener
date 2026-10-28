from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import service
from app.cache import RedirectCache, make_redis
from app.config import get_settings
from app.db import Base, engine, get_db
from app.ratelimit import RateLimiter, enforce
from app.schemas import LinkCreate, LinkOut, LinkStats


@lru_cache
def _redis():
    return make_redis()


def get_cache() -> RedirectCache:
    return RedirectCache(_redis())


def get_limiter() -> RateLimiter:
    return RateLimiter(_redis())


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # swap for Alembic migrations in larger deployments
    yield


app = FastAPI(
    title="URL Shortener",
    description="Scalable URL shortening service with Redis caching and rate limiting.",
    version="1.0.0",
    lifespan=lifespan,
)


def _short_url(code: str) -> str:
    return f"{get_settings().base_url.rstrip('/')}/{code}"


def _to_out(link, model=LinkOut):
    data = {
        "code": link.code,
        "short_url": _short_url(link.code),
        "original_url": link.original_url,
        "created_at": link.created_at,
        "expires_at": link.expires_at,
    }
    if model is LinkStats:
        data["click_count"] = link.click_count
    return model(**data)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.post("/api/links", response_model=LinkOut, status_code=201, tags=["links"])
def create_link(
    payload: LinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    limiter: RateLimiter = Depends(get_limiter),
):
    enforce(limiter, request)
    try:
        link = service.create_link(db, str(payload.url), payload.custom_alias, payload.ttl_seconds)
    except service.AliasTakenError:
        raise HTTPException(status_code=409, detail="Alias already in use")
    except service.CodeGenerationError:
        raise HTTPException(status_code=503, detail="Could not allocate a short code, try again")
    return _to_out(link)


@app.get("/api/links/{code}", response_model=LinkStats, tags=["links"])
def link_stats(code: str, db: Session = Depends(get_db)):
    link = service.get_link(db, code)
    if link is None or link.is_expired():
        raise HTTPException(status_code=404, detail="Link not found")
    return _to_out(link, LinkStats)


@app.delete("/api/links/{code}", status_code=204, tags=["links"])
def delete_link(code: str, db: Session = Depends(get_db), cache: RedirectCache = Depends(get_cache)):
    if not service.delete_link(db, code):
        raise HTTPException(status_code=404, detail="Link not found")
    cache.delete(code)


@app.get("/{code}", tags=["redirect"])
def redirect(code: str, db: Session = Depends(get_db), cache: RedirectCache = Depends(get_cache)):
    # 1) Cache hit: no DB read for the lookup
    url = cache.get(code)
    if url is None:
        # 2) Cache miss: fall back to PostgreSQL
        link = service.get_link(db, code)
        if link is None:
            raise HTTPException(status_code=404, detail="Link not found")
        if link.is_expired():
            raise HTTPException(status_code=410, detail="Link has expired")
        url = link.original_url
        cache.set(code, url, link.expires_at)
    service.record_click(db, code)
    return RedirectResponse(url, status_code=307)
