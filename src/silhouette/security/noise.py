"""Filter operational noise and agent heartbeat reports from memory flows.

Runtime noise (sandbox/exec failures) should not pollute long-term memory.
Heartbeat/scouting reports are valid to store but dilute semantic recall unless
the query is explicitly about them — so they are filtered at recall time only.
"""

from __future__ import annotations

import re
from typing import Any

from silhouette.models import MemoryRecord, ScoredRecord

RUNTIME_NOISE_DIRECT = (
    re.compile(r"exec host\s*=\s*sandbox", re.I),
    re.compile(r"sandbox runtime\s+(?:is\s+)?unavailable", re.I),
    re.compile(r"exec host not allowed", re.I),
    re.compile(r'"tool"\s*:\s*"exec"', re.I),
    re.compile(r"\bsandbox(?:\s+exec)?\s+(?:no disponible|deshabilitad[oa])\b", re.I),
)

AGENT_HEARTBEAT = (
    re.compile(r"\bHEARTBEAT_OK\b", re.I),
    re.compile(r"Scout\s+completado\s*-\s*Ciclo\s+\d+", re.I),
    re.compile(r"\[AGENT:[A-Z]+\].*Ciclo\s+\d+", re.I),
    re.compile(r"Ciclo\s+\d+\s*\(\d{2}:\d{2}\s*UTC\)", re.I),
)


def is_operational_runtime_noise(text: str) -> bool:
    content = (text or "").strip()
    if len(content) < 16:
        return False
    return any(p.search(content) for p in RUNTIME_NOISE_DIRECT)


def should_skip_ingestion(text: str) -> bool:
    return is_operational_runtime_noise(text)


def is_agent_heartbeat_report(text: str) -> bool:
    content = (text or "").strip()
    if len(content) < 10:
        return False
    return any(p.search(content) for p in AGENT_HEARTBEAT)


def filter_heartbeat_records(
    semantic: list[ScoredRecord],
    recent: list[MemoryRecord],
    *,
    filter_heartbeats: bool = True,
) -> tuple[list[ScoredRecord], list[MemoryRecord]]:
    if not filter_heartbeats:
        return semantic, recent
    sem = [s for s in semantic if not is_agent_heartbeat_report(s.record.content)]
    rec = [r for r in recent if not is_agent_heartbeat_report(r.content)]
    return sem, rec


def filter_result_rows(
    rows: list[dict[str, Any]],
    *,
    text_fields: tuple[str, ...] = ("message", "content", "text"),
) -> list[dict[str, Any]]:
    """Drop runtime-noise rows from legacy-style dict results."""
    kept: list[dict[str, Any]] = []
    for row in rows:
        text = ""
        for field in text_fields:
            val = row.get(field)
            if isinstance(val, str) and val:
                text = val
                break
        if not is_operational_runtime_noise(text):
            kept.append(row)
    return kept
