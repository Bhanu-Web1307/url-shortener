import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cache import RedirectCache
from app.config import get_settings
from app.db import Base, get_db
from app.main import app, get_cache, get_limiter
from app.ratelimit import RateLimiter


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(session_factory, redis_client):
    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_cache] = lambda: RedirectCache(redis_client)
    app.dependency_overrides[get_limiter] = lambda: RateLimiter(redis_client)
    # Use TestClient without lifespan so the real Postgres engine is never touched
    c = TestClient(app, follow_redirects=False)
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def settings():
    return get_settings()
