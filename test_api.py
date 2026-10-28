import time
from datetime import timedelta

from app import service
from app.config import get_settings
from app.models import Link, utcnow
from app.shortcode import ALPHABET, generate_code


def create(client, **body):
    body.setdefault("url", "https://example.com/some/long/path?q=1")
    return client.post("/api/links", json=body)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_redirect(client):
    r = create(client)
    assert r.status_code == 201
    data = r.json()
    assert len(data["code"]) == get_settings().code_length
    assert data["short_url"].endswith("/" + data["code"])

    redirect = client.get(f"/{data['code']}")
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "https://example.com/some/long/path?q=1"


def test_invalid_url_rejected(client):
    assert create(client, url="not-a-url").status_code == 422
    assert create(client, url="javascript:alert(1)").status_code == 422


def test_custom_alias_and_conflict(client):
    assert create(client, custom_alias="my-link").status_code == 201
    dup = create(client, custom_alias="my-link")
    assert dup.status_code == 409


def test_bad_or_reserved_alias(client):
    assert create(client, custom_alias="a").status_code == 422
    assert create(client, custom_alias="has space").status_code == 422
    assert create(client, custom_alias="docs").status_code == 422


def test_unknown_code_404(client):
    assert client.get("/doesnotexist").status_code == 404


def test_click_count(client):
    code = create(client).json()["code"]
    for _ in range(3):
        client.get(f"/{code}")
    assert client.get(f"/api/links/{code}").json()["click_count"] == 3


def test_redirect_served_from_cache(client, redis_client, session_factory):
    code = create(client).json()["code"]
    client.get(f"/{code}")  # warms cache
    assert redis_client.get(f"link:{code}") is not None

    # Remove the row behind the cache's back: a cache hit still redirects
    with session_factory() as db:
        db.query(Link).filter(Link.code == code).delete()
        db.commit()
    assert client.get(f"/{code}").status_code == 307


def test_delete_invalidates_cache(client, redis_client):
    code = create(client).json()["code"]
    client.get(f"/{code}")
    assert client.delete(f"/api/links/{code}").status_code == 204
    assert redis_client.get(f"link:{code}") is None
    assert client.get(f"/{code}").status_code == 404


def test_expired_link_returns_410(client, session_factory):
    code = create(client, ttl_seconds=3600).json()["code"]
    with session_factory() as db:
        link = service.get_link(db, code)
        link.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get(f"/{code}").status_code == 410
    assert client.get(f"/api/links/{code}").status_code == 404


def test_ttl_sets_expiry_and_cache_ttl(client, redis_client):
    code = create(client, ttl_seconds=30).json()["code"]
    client.get(f"/{code}")
    ttl = redis_client.ttl(f"link:{code}")
    assert 0 < ttl <= 30


def test_rate_limit(client):
    limit = get_settings().rate_limit_requests
    for _ in range(limit):
        assert create(client).status_code == 201
    blocked = create(client)
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers


def test_collision_retry(session_factory, monkeypatch):
    """If the generator returns a taken code, creation retries and succeeds."""
    codes = iter(["AAAAAAA", "AAAAAAA", "BBBBBBB"])
    monkeypatch.setattr(service, "generate_code", lambda n: next(codes))
    with session_factory() as db:
        first = service.create_link(db, "https://a.com/", None, None)
        second = service.create_link(db, "https://b.com/", None, None)
    assert first.code == "AAAAAAA"
    assert second.code == "BBBBBBB"


def test_generate_code_shape():
    code = generate_code(7)
    assert len(code) == 7 and set(code) <= set(ALPHABET)
    assert len({generate_code(7) for _ in range(1000)}) == 1000
