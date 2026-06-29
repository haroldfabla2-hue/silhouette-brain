"""Janitor engine — keeps memory clean and consistent.

Two jobs:
- **De-duplication:** near-identical episodes (high cosine similarity) are
  collapsed, keeping the most important / most recent copy.
- **Contradiction detection:** episodes that overlap heavily in wording but
  differ in negation polarity (e.g. "I like coffee" vs "I don't like coffee")
  are flagged for review (never silently deleted).
"""

from __future__ import annotations

import re

from silhouette.embeddings.base import cosine_similarity
from silhouette.engines.base import CognitiveEngine
from silhouette.storage.memory import MemorySystem

_NEGATIONS = {
    "no", "not", "never", "n't", "dont", "don't", "doesnt", "doesn't",
    "isnt", "isn't", "nunca", "sin", "odio", "hate", "tampoco",
}
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _has_negation(tokens: set[str]) -> bool:
    return bool(tokens & _NEGATIONS)


class JanitorEngine(CognitiveEngine):
    name = "janitor"

    def __init__(
        self,
        scan_limit: int = 500,
        dup_threshold: float = 0.97,
        overlap_threshold: float = 0.5,
    ) -> None:
        self.scan_limit = scan_limit
        self.dup_threshold = dup_threshold
        self.overlap_threshold = overlap_threshold

    def _execute(self, memory: MemorySystem) -> tuple[str, dict[str, object]]:
        records = memory.episodic.all(limit=self.scan_limit)
        vectors = {r.id: memory.embedder.embed(r.content) for r in records}
        tokens = {r.id: _tokens(r.content) for r in records}

        removed: list[str] = []
        contradictions: list[tuple[str, str]] = []
        alive = list(records)

        for i, a in enumerate(records):
            if a.id in removed:
                continue
            for b in records[i + 1 :]:
                if b.id in removed:
                    continue
                sim = cosine_similarity(vectors[a.id], vectors[b.id])
                if sim >= self.dup_threshold:
                    loser = self._pick_loser(a, b)
                    memory.episodic.delete(loser.id)
                    memory.semantic.delete(loser.id)
                    removed.append(loser.id)
                    continue
                overlap = _jaccard(tokens[a.id], tokens[b.id])
                if overlap >= self.overlap_threshold and (
                    _has_negation(tokens[a.id]) != _has_negation(tokens[b.id])
                ):
                    contradictions.append((a.id, b.id))

        summary = (
            f"Scanned {len(records)} episodes; removed {len(removed)} duplicates; "
            f"flagged {len(contradictions)} contradictions"
        )
        return summary, {
            "scanned": len(records),
            "duplicates_removed": len(removed),
            "contradictions_found": len(contradictions),
            "contradiction_pairs": contradictions,
            "alive_after": len(alive) - len(removed),
        }

    @staticmethod
    def _pick_loser(a, b):
        """Return the record to drop: lower importance, then older."""
        if a.importance != b.importance:
            return a if a.importance < b.importance else b
        return a if a.created_at <= b.created_at else b
