"""The MemorySystem ties the four tiers into one coherent API.

A new memory flows: WORKING (instant) → EPISODIC (durable recent) → SEMANTIC
(embedded for recall) → DEEP (entities/relationships projected into the graph).
Recall fans out across the relevant tiers.
"""

from __future__ import annotations

from collections.abc import Sequence

from silhouette.config import Settings, get_settings
from silhouette.embeddings.base import Embedder
from silhouette.embeddings.factory import get_embedder
from silhouette.errors import MemorySkipped
from silhouette.hooks import emit_memory_stored
from silhouette.models import Entity, MemoryRecord, Relationship, ScoredRecord
from silhouette.security.noise import should_skip_ingestion
from silhouette.storage.entities import extract_entities
from silhouette.storage.episodic import EpisodicStore
from silhouette.storage.graph import GraphStore, get_graph_store
from silhouette.storage.semantic import SemanticStore
from silhouette.storage.working import WorkingMemory


class MemorySystem:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        embedder: Embedder | None = None,
        graph: GraphStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedder = embedder or get_embedder(self.settings)
        self.working = WorkingMemory(self.settings)
        self.episodic = EpisodicStore(self.settings.db_path("episodic.db"))
        self.semantic = SemanticStore(self.settings.db_path("semantic.db"), self.embedder)
        self.graph = graph or get_graph_store(self.settings)

    # -- ingestion ---------------------------------------------------------
    def remember(
        self,
        content: str,
        *,
        importance: float = 0.5,
        tags: list[str] | None = None,
        source: str = "agent",
        link_entities: bool = True,
        apply_noise_filter: bool = True,
    ) -> MemoryRecord:
        """Store a memory across all relevant tiers and return the record.

        Raises :class:`~silhouette.errors.MemorySkipped` when operational noise
        filtering is enabled and the content looks like transient runtime junk.
        """
        if apply_noise_filter and should_skip_ingestion(content):
            raise MemorySkipped("runtime_operational_noise")

        record = MemoryRecord(
            content=content, importance=importance, tags=tags or [], source=source
        )
        self.working.put(record)
        self.episodic.add(record)
        self.semantic.add(record)
        self._project_to_graph(record, link_entities=link_entities)
        emit_memory_stored(record.id, len(extract_entities(content)), source=source)
        return record

    def _project_to_graph(self, record: MemoryRecord, *, link_entities: bool) -> None:
        names = [name for name, _ in extract_entities(record.content)]
        for name, etype in extract_entities(record.content):
            self.graph.upsert_entity(Entity(name=name, type=etype))
        if link_entities:
            # Co-mention edges: every pair of entities seen together is related.
            for i, a in enumerate(names):
                for b in names[i + 1 :]:
                    self.graph.add_relationship(
                        Relationship(source=a, target=b, type="CO_MENTION")
                    )

    # -- recall ------------------------------------------------------------
    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        min_score: float = 0.0,
        tags: Sequence[str] | None = None,
    ) -> list[ScoredRecord]:
        return self.semantic.search(query, limit=limit, min_score=min_score, tags=tags)

    def recent(
        self,
        *,
        hours: float = 24.0,
        limit: int = 20,
        tags: Sequence[str] | None = None,
    ) -> list[MemoryRecord]:
        return self.episodic.recent(hours=hours, limit=limit, tags=tags)

    def entities(self, *, limit: int = 50, etype: str | None = None) -> list[Entity]:
        return self.graph.entities(limit=limit, etype=etype)

    def neighbors(self, name: str, *, limit: int = 20) -> list[Relationship]:
        return self.graph.neighbors(name, limit=limit)

    # -- introspection -----------------------------------------------------
    def stats(self) -> dict[str, object]:
        return {
            "embedder": self.embedder.name,
            "working": len(self.working),
            "episodic": self.episodic.count(),
            "semantic": self.semantic.count(),
            "entities": self.graph.entity_count(),
            "relationships": self.graph.relationship_count(),
        }

    def close(self) -> None:
        self.episodic.close()
        self.semantic.close()
        self.graph.close()
