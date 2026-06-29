"""Dreamer engine — consolidates episodic memory into the deep graph.

Run during low-activity periods. It re-projects recent/important episodes into
the entity graph (idempotent upserts strengthen existing edges) and ensures
every durable episode has a semantic embedding so it is recall-able.
"""

from __future__ import annotations

from silhouette.engines.base import CognitiveEngine
from silhouette.models import Entity, Relationship
from silhouette.storage.entities import extract_entities
from silhouette.storage.memory import MemorySystem


class DreamerEngine(CognitiveEngine):
    name = "dreamer"

    def __init__(self, scan_limit: int = 500, min_importance: float = 0.0) -> None:
        self.scan_limit = scan_limit
        self.min_importance = min_importance

    def _execute(self, memory: MemorySystem) -> tuple[str, dict[str, object]]:
        records = memory.episodic.all(limit=self.scan_limit)
        consolidated = 0
        embedded = 0
        edges_strengthened = 0

        for record in records:
            if record.importance < self.min_importance:
                continue

            # Ensure semantic recall coverage.
            if not memory.semantic.has_embedding(record.id):
                memory.semantic.add(record)
                embedded += 1

            names = [name for name, _ in extract_entities(record.content)]
            for name, etype in extract_entities(record.content):
                memory.graph.upsert_entity(Entity(name=name, type=etype))
            # Strengthen co-mention edges, weighted by importance.
            for i, a in enumerate(names):
                for b in names[i + 1 :]:
                    memory.graph.add_relationship(
                        Relationship(source=a, target=b, type="CO_MENTION",
                                     weight=0.5 + record.importance)
                    )
                    edges_strengthened += 1
            consolidated += 1

        summary = (
            f"Consolidated {consolidated} episodes; embedded {embedded} new; "
            f"strengthened {edges_strengthened} edges"
        )
        return summary, {
            "consolidated": consolidated,
            "embeddings_added": embedded,
            "edges_strengthened": edges_strengthened,
        }
