"""Curiosity engine — proactively surfaces knowledge gaps.

It scans the deep graph for under-connected or rarely-mentioned entities and
formulates investigation questions, storing them in working memory (tagged
``curiosity``) so the agent can choose to follow up. It never fabricates facts —
only questions.
"""

from __future__ import annotations

from silhouette.engines.base import CognitiveEngine
from silhouette.models import MemoryRecord, Tier
from silhouette.storage.memory import MemorySystem


class CuriosityEngine(CognitiveEngine):
    name = "curiosity"

    def __init__(self, max_questions: int = 5, min_mentions: int = 2) -> None:
        self.max_questions = max_questions
        self.min_mentions = min_mentions

    def _execute(self, memory: MemorySystem) -> tuple[str, dict[str, object]]:
        entities = memory.entities(limit=200)
        gaps: list[str] = []
        for entity in entities:
            neighbors = memory.neighbors(entity.name, limit=1)
            # A gap is an entity that is mentioned but barely connected.
            if not neighbors or entity.mention_count < self.min_mentions:
                gaps.append(entity.name)

        questions = [self._question(name) for name in gaps[: self.max_questions]]
        for q in questions:
            memory.working.put(
                MemoryRecord(content=q, tier=Tier.WORKING, importance=0.2,
                             tags=["curiosity", "question"], source="curiosity")
            )

        summary = f"Found {len(gaps)} knowledge gaps; generated {len(questions)} questions"
        return summary, {
            "entities_scanned": len(entities),
            "gaps_found": len(gaps),
            "questions_generated": len(questions),
            "questions": questions,
        }

    @staticmethod
    def _question(name: str) -> str:
        return f"What more do we know about '{name}', and how does it relate to other topics?"
