"""Detect conversation-based prompt injection attempts.

Pattern-based guard inspired by the legacy ``conversation_injection_guard``
module, rewritten for the v3 package with typed results and no side effects in
``check()`` (logging happens only in ``check_and_log``).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("silhouette.security.injection")


class ThreatLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


INJECTION_PATTERNS: list[tuple[str, ThreatLevel]] = [
    (r"(?i)\bignore\s+(all\s+)?(previous|prior|earlier)\s+instructions?", ThreatLevel.CRITICAL),
    (r"(?i)\bdisregard\s+(your\s+)?(system\s+)?prompt", ThreatLevel.CRITICAL),
    (r"(?i)\bforget\s+(what\s+)?(you\s+)?(told|said|know)", ThreatLevel.HIGH),
    (r"(?i)\bnew\s+system\s+prompt\s*:", ThreatLevel.CRITICAL),
    (r"(?i)^\s*system\s*:\s*.", ThreatLevel.CRITICAL),
    (r"(?i)\breveal\s+(your\s+)?(system\s+)?prompt", ThreatLevel.HIGH),
    (r"(?i)\bwhat\s+are\s+your\s+(system\s+)?instructions", ThreatLevel.HIGH),
    (r"(?i)\byou\s+don[\s']?t\s+need\s+to\s+(follow|respect|keep)", ThreatLevel.HIGH),
    (r"(?i)\bDAN\s+mode", ThreatLevel.CRITICAL),
    (r"(?i)\bdo\s+anything\s+now", ThreatLevel.CRITICAL),
    (r'\{[^}]*"role"[^}]*"system"[^}]*\}', ThreatLevel.CRITICAL),
    (r"```system[^`]*```", ThreatLevel.CRITICAL),
]


@dataclass
class InjectionResult:
    threat_level: ThreatLevel
    matched_patterns: list[tuple[str, ThreatLevel]] = field(default_factory=list)
    message: str = ""
    should_block: bool = False
    should_warn: bool = False


class ConversationInjectionGuard:
    def __init__(self) -> None:
        self._patterns = [
            (re.compile(p, re.IGNORECASE | re.MULTILINE), level)
            for p, level in INJECTION_PATTERNS
        ]

    def check(
        self,
        text: str,
        *,
        sender_id: str | None = None,
        channel: str = "unknown",
    ) -> InjectionResult:
        del sender_id  # reserved for future allowlists
        matched: list[tuple[str, ThreatLevel]] = []
        for compiled, level in self._patterns:
            if compiled.search(text or ""):
                matched.append((compiled.pattern, level))

        if not matched:
            return InjectionResult(
                threat_level=ThreatLevel.NONE,
                message="No injection patterns detected",
            )

        levels = [lvl for _, lvl in matched]
        if ThreatLevel.CRITICAL in levels:
            highest = ThreatLevel.CRITICAL
            should_block = True
            should_warn = True
        elif ThreatLevel.HIGH in levels:
            highest = ThreatLevel.HIGH
            should_block = False
            should_warn = True
        elif ThreatLevel.MEDIUM in levels:
            highest = ThreatLevel.MEDIUM
            should_block = False
            should_warn = True
        else:
            highest = ThreatLevel.LOW
            should_block = False
            should_warn = False

        return InjectionResult(
            threat_level=highest,
            matched_patterns=matched,
            message=f"Matched {len(matched)} injection pattern(s) on channel={channel}",
            should_block=should_block,
            should_warn=should_warn,
        )

    def check_and_log(
        self,
        text: str,
        *,
        sender_id: str | None = None,
        channel: str = "unknown",
    ) -> InjectionResult:
        result = self.check(text, sender_id=sender_id, channel=channel)
        if result.should_block:
            logger.warning("[injection] BLOCKED (%s): %s", channel, result.message)
        elif result.should_warn:
            logger.warning("[injection] WARN (%s): %s", channel, result.message)
        return result


_guard: ConversationInjectionGuard | None = None


def check_injection(
    text: str,
    *,
    sender_id: str | None = None,
    channel: str = "unknown",
) -> InjectionResult:
    global _guard
    if _guard is None:
        _guard = ConversationInjectionGuard()
    return _guard.check_and_log(text, sender_id=sender_id, channel=channel)
