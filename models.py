from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The UNIQUE constraint is what makes code generation collision-safe:
    # the database is the source of truth, we simply retry on conflict.
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or utcnow()
        exp = self.expires_at
        if exp.tzinfo is None:  # SQLite returns naive datetimes
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= now
