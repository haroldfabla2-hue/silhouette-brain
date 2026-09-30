"""Fail-closed extractive critic. Source support is not proof of world truth.

Abstractive paraphrases are deliberately unsupported until a separately evaluated
entailment provider exists. Dream text cannot substitute for an episode citation.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from silhouette.models import MemoryRecord


@dataclass(frozen=True)
class EvidenceSpan:
    episode_id: str
    start: int
    end: int
    source_sha256: str


@dataclass(frozen=True)
class SummaryStatement:
    text: str
    citation: EvidenceSpan


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def verify_summary(statements: list[SummaryStatement],
                   resolve: Callable[[str], MemoryRecord | None]) -> list[str]:
    """Check every complete statement against one exact, current source span."""
    errors = []
    if not statements:
        return ['empty summary']
    for index, statement in enumerate(statements):
        citation = statement.citation
        source = resolve(citation.episode_id)
        if source is None:
            errors.append(f'{index}: missing or retracted episode')
            continue
        if content_hash(source.content) != citation.source_sha256:
            errors.append(f'{index}: source changed')
        if (not statement.text.strip() or citation.start < 0
                or citation.end <= citation.start or citation.end > len(source.content)
                or source.content[citation.start:citation.end] != statement.text):
            errors.append(f'{index}: statement is not the cited extract')
    return errors
