"""Async scheduler that drives the cognitive engines and periodic tasks.

Design goals:
- **Non-blocking:** synchronous engine work runs in a thread so the loop stays
  responsive.
- **Observable:** every task exposes its last run, status, and summary; a
  heartbeat file is written each tick.
- **Resilient:** a task raising never stops the scheduler.
- **Testable:** the time source is injectable and a single tick can be driven
  manually.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from silhouette.engines.base import CognitiveEngine
from silhouette.models import EngineResult
from silhouette.storage.memory import MemorySystem

logger = logging.getLogger("silhouette.daemon")

TaskFn = Callable[[], object | Awaitable[object]]


@dataclass
class ScheduledTask:
    name: str
    interval: float
    fn: TaskFn
    next_run: float = 0.0
    last_run: float | None = None
    last_ok: bool | None = None
    last_summary: str = ""
    runs: int = 0

    def is_due(self, now: float) -> bool:
        return now >= self.next_run


class Scheduler:
    def __init__(
        self,
        memory: MemorySystem,
        *,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self.memory = memory
        self._time = time_fn
        self._tasks: dict[str, ScheduledTask] = {}
        self._started_at = self._time()

    # -- registration ------------------------------------------------------
    def add_task(self, name: str, interval: float, fn: TaskFn, *, run_at_start: bool = False) -> None:
        next_run = self._time() if run_at_start else self._time() + interval
        self._tasks[name] = ScheduledTask(name=name, interval=interval, fn=fn, next_run=next_run)

    def add_engine(self, engine: CognitiveEngine, interval: float, **kw) -> None:
        self.add_task(engine.name, interval, lambda: engine.run(self.memory), **kw)

    # -- execution ---------------------------------------------------------
    def _record(self, task: ScheduledTask, result: object, error: Exception | None) -> None:
        if error is not None:
            task.last_ok = False
            task.last_summary = f"{type(error).__name__}: {error}"
            logger.warning("Task '%s' failed: %s", task.name, error)
        elif isinstance(result, EngineResult):
            task.last_ok = result.ok
            task.last_summary = result.summary
        else:
            task.last_ok = True
            task.last_summary = str(result) if result is not None else "ok"
        now = self._time()
        task.last_run = now
        task.runs += 1
        task.next_run = now + task.interval

    def _invoke_sync(self, task: ScheduledTask) -> None:
        try:
            self._record(task, task.fn(), None)
        except Exception as exc:  # error isolation
            self._record(task, None, exc)

    async def _invoke_async(self, task: ScheduledTask) -> None:
        try:
            self._record(task, await task.fn(), None)  # type: ignore[misc]
        except Exception as exc:  # error isolation
            self._record(task, None, exc)

    async def run_due(self, now: float | None = None) -> list[str]:
        """Run all currently-due tasks once; return the names that ran."""
        now = self._time() if now is None else now
        due = [t for t in self._tasks.values() if t.is_due(now)]

        async def dispatch(task: ScheduledTask) -> None:
            # Async tasks run on the loop; synchronous engine work is offloaded
            # to a thread so the loop stays responsive.
            if asyncio.iscoroutinefunction(task.fn):
                await self._invoke_async(task)
            else:
                await asyncio.to_thread(self._invoke_sync, task)

        await asyncio.gather(*(dispatch(t) for t in due))
        if due:
            self.write_heartbeat()
        return [t.name for t in due]

    async def run_forever(
        self,
        *,
        tick: float = 1.0,
        stop_event: asyncio.Event | None = None,
        max_ticks: int | None = None,
    ) -> None:
        logger.info("Scheduler started with %d tasks", len(self._tasks))
        ticks = 0
        while True:
            await self.run_due()
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            if stop_event is not None and stop_event.is_set():
                break
            try:
                if stop_event is not None:
                    await asyncio.wait_for(stop_event.wait(), timeout=tick)
                    break
                else:
                    await asyncio.sleep(tick)
            except asyncio.TimeoutError:
                continue

    # -- introspection -----------------------------------------------------
    def state(self) -> dict[str, object]:
        now = self._time()
        return {
            "uptime_seconds": round(now - self._started_at, 1),
            "tasks": {
                t.name: {
                    "interval": t.interval,
                    "runs": t.runs,
                    "last_ok": t.last_ok,
                    "last_summary": t.last_summary,
                    "seconds_until_next": round(max(0.0, t.next_run - now), 1),
                }
                for t in self._tasks.values()
            },
            "memory": self.memory.stats(),
        }

    def write_heartbeat(self) -> None:
        path = self.memory.settings.db_path("heartbeat_state.json")
        try:
            path.write_text(json.dumps(self.state(), indent=2, default=str), encoding="utf-8")
        except Exception as exc:  # pragma: no cover
            logger.debug("heartbeat write failed: %s", exc)


def build_default_scheduler(memory: MemorySystem) -> Scheduler:
    """Wire the four engines and optional integrations on their intervals."""
    from silhouette.engines import (
        CuriosityEngine,
        DreamerEngine,
        EvolutionEngine,
        JanitorEngine,
    )
    from silhouette.integrations.openclaw import sync_openclaw_sessions

    s = memory.settings
    sched = Scheduler(memory)
    sched.add_engine(CuriosityEngine(), s.curiosity_interval)
    sched.add_engine(JanitorEngine(), s.janitor_interval)
    sched.add_engine(DreamerEngine(), s.dreamer_interval)
    sched.add_engine(EvolutionEngine(), s.evolution_interval)

    if s.openclaw_agents_dir:
        sched.add_task(
            "session_sync",
            s.session_sync_interval,
            lambda: sync_openclaw_sessions(memory, s),
        )
    return sched
