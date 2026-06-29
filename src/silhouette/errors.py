"""Domain-specific exceptions."""


class SilhouetteError(Exception):
    """Base error for the Silhouette Brain package."""


class MemorySkipped(SilhouetteError):
    """Ingestion was intentionally skipped (noise, policy, etc.)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class InjectionBlocked(SilhouetteError):
    """Message blocked by the injection guard."""

    def __init__(self, reason: str, threat_level: str = "critical") -> None:
        self.reason = reason
        self.threat_level = threat_level
        super().__init__(reason)
