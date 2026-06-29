"""Typed domain models shared across the system.

These are intentionally framework-agnostic Pydantic models so they can be used
identically by the storage layer, the cognitive engines, and the HTTP API.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum

from pydantic import BaseModel, Field


class Tier(str, Enum):
    """The four memory tiers, from fastest/most-ephemeral to deepest."""

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    DEEP = "deep"


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> float:
    return time.time()


class MemoryRecord(BaseModel):
    """A single unit of memory.

    A record can live in one or more tiers over its lifetime: it is born in
    WORKING, consolidated into EPISODIC, embedded for SEMANTIC recall, and its
    entities/relations are projected into the DEEP graph.
    """

    id: str = Field(default_factory=_new_id)
    content: str
    tier: Tier = Tier.WORKING
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    source: str = "unknown"
    created_at: float = Field(default_factory=_now)
    last_access: float = Field(default_factory=_now)
    access_count: int = 0
    # Populated once the record has been embedded for semantic search.
    embedding: list[float] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    def touch(self) -> None:
        self.last_access = _now()
        self.access_count += 1


class Entity(BaseModel):
    """A named thing extracted from memories (person, project, concept...)."""

    name: str
    type: str = "concept"
    mention_count: int = 1
    first_seen: float = Field(default_factory=_now)
    last_seen: float = Field(default_factory=_now)
    metadata: dict[str, object] = Field(default_factory=dict)


class Relationship(BaseModel):
    """A directed edge between two entities in the deep graph."""

    source: str
    target: str
    type: str = "RELATED_TO"
    weight: float = 1.0
    metadata: dict[str, object] = Field(default_factory=dict)


class ScoredRecord(BaseModel):
    """A record paired with a relevance score from a retrieval pass."""

    record: MemoryRecord
    score: float = 0.0
    origin: str = "unknown"


class ContextPacket(BaseModel):
    """The assembled, budget-bounded context returned to an agent."""

    query: str
    semantic: list[ScoredRecord] = Field(default_factory=list)
    recent: list[MemoryRecord] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    graph: list[Relationship] = Field(default_factory=list)
    synthesis: str | None = None
    token_estimate: int = 0
    sources_used: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0


class EngineResult(BaseModel):
    """Structured outcome of one cognitive-engine cycle."""

    engine: str
    ok: bool = True
    started_at: float = Field(default_factory=_now)
    duration_ms: float = 0.0
    summary: str = ""
    stats: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
