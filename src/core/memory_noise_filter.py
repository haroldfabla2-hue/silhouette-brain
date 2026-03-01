#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Runtime noise filters for long-term memory ingestion and recall.

This module blocks transient operational failures (sandbox/exec/config mismatch)
from contaminating semantic memory while still allowing runtime diagnostics when
the current query is explicitly about that topic.
"""
import re
from typing import Any, Dict, Iterable, List, Sequence

RUNTIME_NOISE_DIRECT_PATTERNS: Sequence[re.Pattern] = (
    re.compile(r"exec host\s*=\s*sandbox", re.IGNORECASE),
    re.compile(r"sandbox runtime\s+(?:is\s+)?unavailable", re.IGNORECASE),
    re.compile(r"exec host not allowed", re.IGNORECASE),
    re.compile(r"tools\.exec\.host", re.IGNORECASE),
    re.compile(r"agents\.defaults\.sandbox\.mode", re.IGNORECASE),
    re.compile(r"configure tools\.exec\.host", re.IGNORECASE),
    re.compile(r'"tool"\s*:\s*"exec"', re.IGNORECASE),
    re.compile(r"\bexec(?:\s+est[aá])?\s+deshabilitad[oa]\b", re.IGNORECASE),
    re.compile(r"\bejecutor(?:\s+de\s+comandos)?(?:\s+est[aá])?\s+deshabilitad[oa]\b", re.IGNORECASE),
    re.compile(r"\bsandbox(?:\s+exec)?\s+(?:no disponible|deshabilitad[oa]|bloquead[oa])\b", re.IGNORECASE),
    re.compile(r"\bsandbox\s+runtime\s+no\s+est[aá]\s+disponible\b", re.IGNORECASE),
    re.compile(r"\bsandbox\s+exec\b[^\n]{0,40}\bno\s+disponible\b", re.IGNORECASE),
)

RUNTIME_NOISE_SOFT_PATTERNS: Sequence[re.Pattern] = (
    re.compile(r"\bhabilitar\s+el\s+sandbox\b", re.IGNORECASE),
    re.compile(r"\bno puedo(?:\s+\w+){0,8}\s+(?:ejecutar|usar)\s+comandos\b", re.IGNORECASE),
)

# Patterns for automated agent heartbeat/scouting reports.
# These are legitimate data but dilute semantic search relevance when used
# as context injection. Filter them from auto-recall, NOT from ingestion.
AGENT_HEARTBEAT_PATTERNS: Sequence[re.Pattern] = (
    re.compile(r"\bHEARTBEAT_OK\b", re.IGNORECASE),
    re.compile(r"Scout\s+completado\s*[-–]\s*Ciclo\s+\d+", re.IGNORECASE),
    re.compile(r"\[AGENT:[A-Z]+\].*Ciclo\s+\d+", re.IGNORECASE),
    re.compile(r"\|\s*(?:Oportunidades|High Priority|Medium Priority)\s*\|.*\|", re.IGNORECASE),
    re.compile(r"Ciclo\s+\d+\s*\(\d{2}:\d{2}\s*UTC\)", re.IGNORECASE),
    re.compile(r"\bstandup\b.*\d{4}-\d{2}-\d{2}", re.IGNORECASE),
    re.compile(r"Senior\s+\w+\s+(?:Engineer|Developer).*\$[\d,k+]+", re.IGNORECASE),
)

RUNTIME_DIAGNOSTIC_QUERY_PATTERNS: Sequence[re.Pattern] = (
    re.compile(r"\bsandbox\b", re.IGNORECASE),
    re.compile(r"\btools\.exec\.host\b", re.IGNORECASE),
    re.compile(r"\bagents\.defaults\.sandbox\.mode\b", re.IGNORECASE),
    re.compile(r"\bexec\b", re.IGNORECASE),
    re.compile(r"\bejecutor\b", re.IGNORECASE),
    re.compile(r"\bhost not allowed\b", re.IGNORECASE),
    re.compile(r"\bhost=sandbox\b", re.IGNORECASE),
    re.compile(r"\bconfigur(?:a|ar|acion)\b", re.IGNORECASE),
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def is_runtime_diagnostic_query(query: str) -> bool:
    text = _as_text(query).strip().lower()
    if len(text) < 3:
        return False
    return any(pattern.search(text) for pattern in RUNTIME_DIAGNOSTIC_QUERY_PATTERNS)


def is_operational_runtime_noise(text: str) -> bool:
    content = _as_text(text)
    if len(content.strip()) < 16:
        return False
    lowered = content.lower()

    if any(pattern.search(lowered) for pattern in RUNTIME_NOISE_DIRECT_PATTERNS):
        return True

    # Soft patterns must still mention runtime-exec/sandbox terms.
    if any(pattern.search(lowered) for pattern in RUNTIME_NOISE_SOFT_PATTERNS):
        if "sandbox" in lowered or "exec" in lowered or "ejecutor" in lowered:
            return True

    return False


def should_skip_ingestion(text: str) -> bool:
    return is_operational_runtime_noise(text)


def is_agent_heartbeat_report(text: str) -> bool:
    """Return True if text looks like an automated agent heartbeat/scouting report.

    These messages are valid data and SHOULD be stored in memory, but they
    dilute semantic search quality when injected as context for unrelated
    queries.  Use this only to filter auto-recall context injection, not
    for ingestion filtering.
    """
    content = _as_text(text)
    if len(content.strip()) < 10:
        return False
    return any(pattern.search(content) for pattern in AGENT_HEARTBEAT_PATTERNS)


def should_filter_for_query(text: str, query: str) -> bool:
    if is_runtime_diagnostic_query(query):
        return False
    return is_operational_runtime_noise(text)


def filter_result_rows(
    rows: Iterable[Dict[str, Any]],
    query: str = "",
    text_fields: Sequence[str] = ("message", "content", "text"),
) -> List[Dict[str, Any]]:
    allow_runtime = is_runtime_diagnostic_query(query)
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        text = ""
        for field in text_fields:
            value = row.get(field)
            if isinstance(value, str) and value:
                text = value
                break
        if allow_runtime or not is_operational_runtime_noise(text):
            filtered.append(row)
    return filtered
