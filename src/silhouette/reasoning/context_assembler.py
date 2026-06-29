"""Assemble a budget-bounded context packet across the memory tiers."""

from __future__ import annotations

import time

from silhouette.models import ContextPacket, MemoryRecord, ScoredRecord
from silhouette.reasoning.synthesizer import Synthesizer
from silhouette.security.noise import filter_heartbeat_records
from silhouette.storage.entities import extract_entities
from silhouette.storage.memory import MemorySystem


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), min 1 for non-empty text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class ContextAssembler:
    def __init__(self, memory: MemorySystem, synthesizer: Synthesizer | None = None) -> None:
        self.memory = memory
        self.synthesizer = synthesizer

    def assemble(
        self,
        query: str,
        *,
        sem_limit: int = 5,
        rec_limit: int = 3,
        hours: float = 2.0,
        min_score: float = 0.1,
        include_entities: bool = True,
        include_graph: bool = False,
        token_budget: int | None = None,
        synthesize: bool = False,
        filter_heartbeats: bool = True,
    ) -> ContextPacket:
        start = time.perf_counter()
        sources: list[str] = []

        semantic = self.memory.recall(query, limit=sem_limit, min_score=min_score)
        recent = self.memory.recent(hours=hours, limit=rec_limit)
        semantic, recent = filter_heartbeat_records(
            semantic, recent, filter_heartbeats=filter_heartbeats
        )
        if semantic:
            sources.append("semantic")
        if recent:
            sources.append("recent")

        entities = self.memory.entities(limit=10) if include_entities else []
        if entities:
            sources.append("entities")

        graph: list = []
        if include_graph:
            query_entity_names = [n for n, _ in extract_entities(query)]
            seen: set[tuple[str, str, str]] = set()
            for name in query_entity_names or [e.name for e in entities[:3]]:
                for rel in self.memory.neighbors(name, limit=5):
                    key = (rel.source, rel.target, rel.type)
                    if key not in seen:
                        seen.add(key)
                        graph.append(rel)
            if graph:
                sources.append("graph")

        if token_budget is not None:
            semantic, recent = self._prune(semantic, recent, token_budget)

        packet = ContextPacket(
            query=query,
            semantic=semantic,
            recent=recent,
            entities=entities,
            graph=graph,
            sources_used=sources,
        )
        packet.token_estimate = self._count_tokens(semantic, recent)

        if synthesize and self.synthesizer is not None:
            packet.synthesis = self.synthesizer.synthesize(query, semantic, recent)
            packet.sources_used.append(f"synthesis:{self.synthesizer.name}")

        packet.latency_ms = (time.perf_counter() - start) * 1000.0
        return packet

    @staticmethod
    def _count_tokens(
        semantic: list[ScoredRecord], recent: list[MemoryRecord]
    ) -> int:
        total = sum(estimate_tokens(s.record.content) for s in semantic)
        total += sum(estimate_tokens(r.content) for r in recent)
        return total

    def _prune(
        self,
        semantic: list[ScoredRecord],
        recent: list[MemoryRecord],
        budget: int,
    ) -> tuple[list[ScoredRecord], list[MemoryRecord]]:
        """Greedily keep highest-value items until the token budget is hit.

        Semantic results (ranked by score) are prioritized over recent ones.
        """
        kept_sem: list[ScoredRecord] = []
        used = 0
        for s in semantic:
            cost = estimate_tokens(s.record.content)
            if used + cost > budget:
                break
            kept_sem.append(s)
            used += cost
        kept_recent: list[MemoryRecord] = []
        for r in recent:
            cost = estimate_tokens(r.content)
            if used + cost > budget:
                break
            kept_recent.append(r)
            used += cost
        return kept_sem, kept_recent
