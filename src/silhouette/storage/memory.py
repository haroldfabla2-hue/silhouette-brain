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
from silhouette.storage._tags import matches_tags, normalize_tags
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
        self.reconcile()

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
        self.episodic.queue(record, link_entities=link_entities)
        # Durable source is committed before any cache or projection is touched.
        self.reconcile()
        self.working.put(record)
        emit_memory_stored(record.id, len(extract_entities(content)), source=source)
        return record

    def reconcile(self) -> int:
        """Replay unfinished projection work; safe across crashes and restarts.

        A failed projection raises, leaving the source and outbox entry intact.
        Each consumer checks its persisted result before acknowledging.
        """
        completed = 0
        for job in self.episodic.pending():
            record_id, version, operation = job["id"], job["version"], job["operation"]
            record = self.episodic.get(record_id) if operation == "upsert" else None
            if operation == "upsert" and (record is None or self.episodic.version(record) != version):
                raise RuntimeError(f"Outbox/source mismatch: {record_id}")
            if not job["semantic_done"]:
                if record is None:
                    self.semantic.delete(record_id)
                    if self.semantic.has_embedding(record_id):
                        raise RuntimeError("Semantic deletion not verified")
                else:
                    self.semantic.add(record)
                    if not self.semantic.matches(record):
                        raise RuntimeError("Semantic projection not verified")
                self.episodic.mark_done(record_id, version, operation, "semantic")
            if not job["graph_done"]:
                if record is None:
                    self.graph.retract_episode(record_id)
                else:
                    entities = extract_entities(record.content)
                    names = [name for name, _ in entities]
                    edges = ([(a, b, "CO_MENTION", 1.0)
                              for i, a in enumerate(names) for b in names[i + 1:]]
                             if job["link_entities"] else [])
                    self.graph.apply_episode(record_id, entities, edges)
                if record is None and self.graph.has_episode(record_id):
                    raise RuntimeError("Graph retraction not verified")
                if record is not None and extract_entities(record.content) and not self.graph.has_episode(record_id):
                    raise RuntimeError("Graph projection not verified")
                self.episodic.mark_done(record_id, version, operation, "graph")
            completed += 1
        return completed

    # -- recall ------------------------------------------------------------
    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        min_score: float = 0.0,
        tags: Sequence[str] | None = None,
    ) -> list[ScoredRecord]:
        # A tombstone hides stale semantic rows while retraction is pending.
        hits = self.semantic.search(query, limit=self.semantic.count(), min_score=min_score, tags=tags)
        return [hit for hit in hits if self.episodic.get(hit.record.id) is not None][:limit]

    def recent(
        self,
        *,
        hours: float = 24.0,
        limit: int = 20,
        tags: Sequence[str] | None = None,
    ) -> list[MemoryRecord]:
        return self.episodic.recent(hours=hours, limit=limit, tags=tags)

    def forget(self, record_id: str) -> bool:
        """Queue retraction before removing cached copies and return only after verification.

        Projection failure is raised, not converted to a false success. A
        subsequent reconcile retries pending cleanup after process restart.
        """
        existed = self.episodic.tombstone(record_id)
        if not existed:
            return False
        self.reconcile()
        self.working.discard(record_id)
        return True

    def forget_tagged(self, tags: Sequence[str], *, scan_limit: int = 10000) -> int:
        """Delete every memory carrying at least one of ``tags``.

        Returns how many were removed. An empty ``tags`` deletes nothing: a
        blank filter must never be read as "delete everything".
        """
        wanted = normalize_tags(tags)
        if not wanted:
            return 0
        objetivo = [
            record.id
            for record in self.episodic.all(limit=scan_limit)
            if matches_tags(record.tags, wanted)
        ]
        return sum(1 for record_id in objetivo if self.forget(record_id))

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
