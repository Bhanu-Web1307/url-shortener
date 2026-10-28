"""Business logic for creating and resolving links."""
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Link, utcnow
from app.shortcode import generate_code


class AliasTakenError(Exception):
    pass


class CodeGenerationError(Exception):
    pass


def _expiry(ttl_seconds: int | None):
    s = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else s.default_ttl_seconds
    if ttl is None:
        return None
    ttl = min(ttl, s.max_ttl_seconds)
    return utcnow() + timedelta(seconds=ttl)


def create_link(db: Session, url: str, custom_alias: str | None, ttl_seconds: int | None) -> Link:
    s = get_settings()
    expires_at = _expiry(ttl_seconds)

    if custom_alias:
        link = Link(code=custom_alias, original_url=url, expires_at=expires_at)
        db.add(link)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise AliasTakenError(custom_alias)
        return link

    # Random code; the UNIQUE constraint detects collisions, we retry.
    for _ in range(s.max_code_retries):
        link = Link(code=generate_code(s.code_length), original_url=url, expires_at=expires_at)
        db.add(link)
        try:
            db.commit()
            return link
        except IntegrityError:
            db.rollback()
    raise CodeGenerationError("could not allocate a unique short code")


def get_link(db: Session, code: str) -> Link | None:
    return db.scalar(select(Link).where(Link.code == code))


def record_click(db: Session, code: str) -> None:
    # Atomic increment in SQL, safe under concurrent redirects.
    db.execute(update(Link).where(Link.code == code).values(click_count=Link.click_count + 1))
    db.commit()


def delete_link(db: Session, code: str) -> bool:
    link = get_link(db, code)
    if link is None:
        return False
    db.delete(link)
    db.commit()
    return True
