"""Request/response schemas for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RememberRequest(BaseModel):
    content: str = Field(min_length=1)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    source: str = "agent"
    channel: str = "unknown"
    sender_id: str | None = None


class RememberResponse(BaseModel):
    id: str | None = None
    status: str = "ok"
    reason: str | None = None
    threat: str | None = None
