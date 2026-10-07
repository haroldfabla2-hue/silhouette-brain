"""Assemble a budget-bounded context packet across the memory tiers."""

from __future__ import annotations

import re
import time
from collections.abc import Sequence

from silhouette.models import (
    ContextPacket,
    Entity,
    MemoryRecord,
    Relationship,
    ScoredRecord,
)
from silhouette.reasoning.synthesizer import Synthesizer
from silhouette.security.noise import filter_heartbeat_records
from silhouette.storage.entities import extract_entities
from silhouette.storage.memory import MemorySystem


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), min 1 for non-empty text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _entity_tokens(entity: Entity) -> int:
    return estimate_tokens(f"{entity.name} {entity.type}")


def _relation_tokens(rel: Relationship) -> int:
    return estimate_tokens(f"{rel.source} {rel.type} {rel.target}")


def _dedupe(
    semantic: list[ScoredRecord], recent: list[MemoryRecord]
) -> tuple[list[ScoredRecord], list[MemoryRecord]]:
    """Drop records that appear in both lists (semantic keeps its copy).

    Injecting the same memory twice wastes budget and can bias the agent
    towards a duplicated fact. Semantic results carry a relevance score, so
    they win over the bare recency copy.
    """
    seen = {s.record.id for s in semantic}
    return semantic, [r for r in recent if r.id not in seen]


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
        budget_split: tuple[float, float, float] = (0.60, 0.25, 0.15),
        synthesize: bool = False,
        filter_heartbeats: bool = True,
        tags: Sequence[str] | None = None,
    ) -> ContextPacket:
        """Build a context packet for ``query``.

        Quality rules (all opt-out via arguments, defaults improved):
        - semantic/recent results are de-duplicated by record id;
        - entities are injected only when relevant to the query (an entity
          name must appear in the query text); there is no arbitrary global
          top-10 fallback;
        - graph relations are fetched only for entities mentioned in the
          query, never for unrelated top entities;
        - ``token_budget`` covers every source (semantic, recent, entities
          and graph) split by ``budget_split`` fractions.
        """
        start = time.perf_counter()
        sources: list[str] = []

        semantic = self.memory.recall(
            query, limit=sem_limit, min_score=min_score, tags=tags
        )
        recent = self.memory.recent(hours=hours, limit=rec_limit, tags=tags)
        semantic, recent = filter_heartbeat_records(
            semantic, recent, filter_heartbeats=filter_heartbeats
        )
        semantic, recent = _dedupe(semantic, recent)
        if semantic:
            sources.append("semantic")
        if recent:
            sources.append("recent")

        entities = self._relevant_entities(query) if include_entities else []
        if entities:
            sources.append("entities")

        graph: list[Relationship] = []
        if include_graph:
            query_entity_names = [n for n, _ in extract_entities(query)]
            seen: set[tuple[str, str, str]] = set()
            for name in query_entity_names:
                for rel in self.memory.neighbors(name, limit=5):
                    key = (rel.source, rel.target, rel.type)
                    if key not in seen:
                        seen.add(key)
                        graph.append(rel)
            if graph:
                sources.append("graph")

        if token_budget is not None:
            semantic, recent, entities, graph = self._prune(
                semantic, recent, entities, graph, token_budget, budget_split
            )

        packet = ContextPacket(
            query=query,
            semantic=semantic,
            recent=recent,
            entities=entities,
            graph=graph,
            sources_used=sources,
        )
        packet.token_estimate = self._count_tokens(semantic, recent, entities, graph)

        if synthesize and self.synthesizer is not None:
            packet.synthesis = self.synthesizer.synthesize(query, semantic, recent)
            packet.sources_used.append(f"synthesis:{self.synthesizer.name}")

        packet.latency_ms = (time.perf_counter() - start) * 1000.0
        return packet

    def _relevant_entities(self, query: str, limit: int = 10) -> list[Entity]:
        """Entities whose name appears in the query, most-mentioned first."""
        needle = query.lower()
        # Whole-word match: a short entity name must not match inside another word.
        found = [
            e
            for e in self.memory.entities(limit=50)
            if re.search(r"\b" + re.escape(e.name.lower()) + r"\b", needle)
        ]
        return sorted(found, key=lambda e: e.mention_count, reverse=True)[:limit]

    @staticmethod
    def _count_tokens(
        semantic: list[ScoredRecord],
        recent: list[MemoryRecord],
        entities: list[Entity],
        graph: list[Relationship],
    ) -> int:
        total = sum(estimate_tokens(s.record.content) for s in semantic)
        total += sum(estimate_tokens(r.content) for r in recent)
        total += sum(_entity_tokens(e) for e in entities)
        total += sum(_relation_tokens(r) for r in graph)
        return total

    def _prune(
        self,
        semantic: list[ScoredRecord],
        recent: list[MemoryRecord],
        entities: list[Entity],
        graph: list[Relationship],
        budget: int,
        split: tuple[float, float, float],
    ) -> tuple[list[ScoredRecord], list[MemoryRecord], list[Entity], list[Relationship]]:
        """Greedily keep highest-value items per source within its share.

        ``split`` = (semantic, recent, entities+graph) fractions of the total
        budget. Semantic results (ranked by score) come first inside their
        share; recency order is preserved inside the recent share.
        """
        sem_share, rec_share, aux_share = split
        if sem_share < 0 or rec_share < 0 or aux_share < 0 or sem_share + rec_share + aux_share <= 0:
            raise ValueError(f"invalid budget_split: {split}")

        kept_sem: list[ScoredRecord] = []
        used = 0
        sem_cap = int(budget * sem_share)
        for s in semantic:
            cost = estimate_tokens(s.record.content)
            if used + cost > sem_cap:
                break
            kept_sem.append(s)
            used += cost

        kept_recent: list[MemoryRecord] = []
        used = 0
        rec_cap = int(budget * rec_share)
        for r in recent:
            cost = estimate_tokens(r.content)
            if used + cost > rec_cap:
                break
            kept_recent.append(r)
            used += cost

        aux_cap = int(budget * aux_share)
        kept_entities: list[Entity] = []
        used = 0
        for e in entities:
            cost = _entity_tokens(e)
            if used + cost > aux_cap:
                break
            kept_entities.append(e)
            used += cost
        kept_graph: list[Relationship] = []
        for rel in graph:
            cost = _relation_tokens(rel)
            if used + cost > aux_cap:
                break
            kept_graph.append(rel)
            used += cost

        return kept_sem, kept_recent, kept_entities, kept_graph
