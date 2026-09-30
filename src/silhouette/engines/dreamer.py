"""Dreamer replays source episodes without promoting unverified assertions.

A bounded, deterministic priority pass favors explicit salience and diversity.
Creative output and factual summaries require separate verification before any
promotion and are intentionally not created by this engine.
"""

from __future__ import annotations

from silhouette.engines.base import CognitiveEngine
from silhouette.storage.activation import activation_score
from silhouette.storage.entities import extract_entities
from silhouette.storage.memory import MemorySystem


class DreamerEngine(CognitiveEngine):
    name = "dreamer"

    def __init__(self, scan_limit: int = 500, min_importance: float = 0.0,
                 budget: int = 100) -> None:
        self.scan_limit = scan_limit
        self.min_importance = min_importance
        self.budget = budget

    def _execute(self, memory: MemorySystem) -> tuple[str, dict[str, object]]:
        candidates = memory.episodic.all(limit=self.scan_limit)
        # Stable order regardless of SQLite's tie order; never trust a dream as evidence.
        candidates.sort(key=lambda r: (-float(activation_score(
            r.created_at, memory.episodic.access_history(r.id),
            importance=r.importance)["score"]), r.id))
        consolidated = 0
        embedded = 0
        edges_replayed = 0
        seen_entities: set[str] = set()
        deferred = []
        selected = []
        for record in candidates:
            if record.importance < self.min_importance:
                continue
            names = {name for name, _ in extract_entities(record.content)}
            if names and names <= seen_entities:
                deferred.append(record)
            else:
                selected.append(record)
                seen_entities.update(names)
        selected.extend(deferred)

        for record in selected[:max(0, self.budget)]:
            if not memory.semantic.has_embedding(record.id):
                embedded += 1
            memory.episodic.queue(record)
            memory.reconcile()
            projected_names = [name for name, _ in extract_entities(record.content)]
            edges_replayed += len(projected_names) * (len(projected_names) - 1) // 2
            consolidated += 1

        summary = f"Replayed {consolidated} episodes; embedded {embedded} new"
        return summary, {
            "consolidated": consolidated,
            "embeddings_added": embedded,
            "edges_replayed": edges_replayed,
            # Keep old metric name for callers, though P0 replay does not strengthen.
            "edges_strengthened": 0,
        }
