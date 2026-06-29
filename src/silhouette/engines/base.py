"""Base class for cognitive engines.

An engine is a self-contained background process that reads and reshapes the
memory system. The base handles timing and error isolation so a crashing engine
can never take down the daemon; subclasses implement :meth:`_execute`.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from silhouette.models import EngineResult
from silhouette.storage.memory import MemorySystem


class CognitiveEngine(ABC):
    #: Stable identifier used in logs, schedules and results.
    name: str = "engine"

    @abstractmethod
    def _execute(self, memory: MemorySystem) -> tuple[str, dict[str, object]]:
        """Do the work. Return ``(human_summary, stats)``."""

    def run(self, memory: MemorySystem) -> EngineResult:
        start = time.perf_counter()
        result = EngineResult(engine=self.name, started_at=time.time())
        try:
            summary, stats = self._execute(memory)
            result.summary = summary
            result.stats = stats
            result.ok = True
        except Exception as exc:  # error isolation
            result.ok = False
            result.error = f"{type(exc).__name__}: {exc}"
            result.summary = "engine failed"
        result.duration_ms = (time.perf_counter() - start) * 1000.0
        return result
