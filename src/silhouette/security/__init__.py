"""Security helpers: prompt-injection detection and ingestion noise filtering."""

from silhouette.security.injection import (
    ConversationInjectionGuard,
    InjectionResult,
    ThreatLevel,
    check_injection,
)
from silhouette.security.noise import (
    filter_heartbeat_records,
    is_agent_heartbeat_report,
    is_operational_runtime_noise,
    should_skip_ingestion,
)

__all__ = [
    "ConversationInjectionGuard",
    "InjectionResult",
    "ThreatLevel",
    "check_injection",
    "filter_heartbeat_records",
    "is_agent_heartbeat_report",
    "is_operational_runtime_noise",
    "should_skip_ingestion",
]
