import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
RESERVED = {"api", "docs", "redoc", "openapi.json", "health", "static"}


class LinkCreate(BaseModel):
    url: HttpUrl
    custom_alias: str | None = Field(default=None, description="Optional vanity code, 3-32 chars [A-Za-z0-9_-]")
    ttl_seconds: int | None = Field(default=None, gt=0, description="Seconds until the link expires")

    @field_validator("custom_alias")
    @classmethod
    def validate_alias(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not ALIAS_RE.match(v):
            raise ValueError("alias must be 3-32 chars of letters, digits, '_' or '-'")
        if v.lower() in RESERVED:
            raise ValueError("alias is reserved")
        return v


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None


class LinkStats(LinkOut):
    click_count: int
