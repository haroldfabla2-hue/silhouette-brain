"""Silhouette Brain — a 4-tier cognitive memory system for AI agents.

The package is layered and dependency-light by default:

- ``silhouette.models``    — typed domain objects (records, entities, packets).
- ``silhouette.config``    — environment-driven settings.
- ``silhouette.embeddings``— pluggable embedders (dependency-free fallback).
- ``silhouette.storage``   — the four memory tiers + the orchestrating system.
- ``silhouette.reasoning`` — context assembly and optional synthesis.
- ``silhouette.engines``   — Curiosity, Janitor, Dreamer, Evolution.
- ``silhouette.daemon``    — async scheduler that runs the engines.
- ``silhouette.api``       — FastAPI HTTP surface.

Everything runs with zero external services out of the box (SQLite + an
in-memory graph + a hashing embedder). Production backends (Redis, Neo4j,
fastembed) activate automatically when configured and installed.
"""

from silhouette.config import Settings, get_settings
from silhouette.models import (
    ContextPacket,
    Entity,
    MemoryRecord,
    Relationship,
    Tier,
)

__version__ = "3.0.0"

__all__ = [
    "ContextPacket",
    "Entity",
    "MemoryRecord",
    "Relationship",
    "Settings",
    "Tier",
    "__version__",
    "get_settings",
]
