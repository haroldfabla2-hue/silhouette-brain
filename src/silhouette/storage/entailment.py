"""Evidence-bound NLI review groundwork; model scores never accept claims.

No provider is bundled and no neural quality is claimed. An adapter must be
separately evaluated before use. Exact extracts work without model inference.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from silhouette.models import MemoryRecord
from silhouette.storage.critic import SummaryStatement, content_hash


@dataclass(frozen=True)
class EntailmentScores:
    entailment: float
    contradiction: float
    neutral: float


class EntailmentProvider(Protocol):
    name: str
    revision: str

    def score(self, premise: str, hypothesis: str) -> EntailmentScores: ...


@dataclass(frozen=True)
class EvidenceReview:
    status: str
    reason: str
    provider: str | None = None
    revision: str | None = None
    scores: EntailmentScores | None = None


def review_statement(statement: SummaryStatement,
                     resolve: Callable[[str], MemoryRecord | None], *,
                     provider: EntailmentProvider | None = None) -> EvidenceReview:
    """Return review advice only. No ACCEPTED state or knowledge-store mutation."""
    citation = statement.citation
    source = resolve(citation.episode_id)
    if source is None:
        return EvidenceReview('REJECTED', 'Missing or retracted episode')
    if content_hash(source.content) != citation.source_sha256:
        return EvidenceReview('REJECTED', 'Source changed')
    if (citation.start < 0 or citation.end <= citation.start
            or citation.end > len(source.content) or not statement.text.strip()):
        return EvidenceReview('REJECTED', 'Invalid evidence span or empty statement')
    premise = source.content[citation.start:citation.end]
    if statement.text == premise:
        return EvidenceReview('VERIFIED_EXTRACT', 'Exact current source span; not world truth')
    if provider is None:
        return EvidenceReview('NEEDS_OWNER_REVIEW', 'Paraphrase requires an evaluated NLI provider')
    if not provider.name.strip() or not provider.revision.strip():
        return EvidenceReview('NEEDS_OWNER_REVIEW', 'Unversioned provider')
    try:
        scores = provider.score(premise, statement.text)
        values = (scores.entailment, scores.contradiction, scores.neutral)
        if (any(not math.isfinite(x) or not 0 <= x <= 1 for x in values)
                or not math.isclose(sum(values), 1.0, abs_tol=1e-4)):
            return EvidenceReview('NEEDS_OWNER_REVIEW', 'Invalid provider probabilities')
    except Exception:
        return EvidenceReview('NEEDS_OWNER_REVIEW', 'Provider inference failed')
    # Re-resolve after potentially slow inference; never report stale model advice.
    current = resolve(citation.episode_id)
    if current is None or content_hash(current.content) != citation.source_sha256:
        return EvidenceReview('REJECTED', 'Evidence changed during inference')
    return EvidenceReview('NEEDS_OWNER_REVIEW', 'Model advice is not approval',
                          provider.name, provider.revision, scores)
