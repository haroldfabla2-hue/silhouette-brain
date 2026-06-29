import asyncio

from silhouette.daemon import Scheduler, build_default_scheduler
from silhouette.engines import CuriosityEngine


class FakeClock:
    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


async def test_task_runs_when_due(memory):
    clock = FakeClock()
    sched = Scheduler(memory, time_fn=clock)
    calls = []
    sched.add_task("ping", interval=10.0, fn=lambda: calls.append(1))

    ran = await sched.run_due()
    assert ran == []  # not due yet (next_run = now + interval)

    clock.advance(11)
    ran = await sched.run_due()
    assert ran == ["ping"]
    assert len(calls) == 1


async def test_run_at_start(memory):
    clock = FakeClock()
    sched = Scheduler(memory, time_fn=clock)
    calls = []
    sched.add_task("boot", interval=10.0, fn=lambda: calls.append(1), run_at_start=True)
    ran = await sched.run_due()
    assert ran == ["boot"]


async def test_engine_task_records_result(memory):
    memory.remember("Madrid is a city")
    clock = FakeClock()
    sched = Scheduler(memory, time_fn=clock)
    sched.add_engine(CuriosityEngine(min_mentions=5), interval=60.0, run_at_start=True)
    await sched.run_due()
    state = sched.state()
    assert state["tasks"]["curiosity"]["runs"] == 1
    assert state["tasks"]["curiosity"]["last_ok"] is True


async def test_failing_task_is_isolated(memory):
    clock = FakeClock()
    sched = Scheduler(memory, time_fn=clock)

    def boom():
        raise ValueError("nope")

    sched.add_task("boom", interval=5.0, fn=boom, run_at_start=True)
    sched.add_task("ok", interval=5.0, fn=lambda: "fine", run_at_start=True)
    await sched.run_due()
    state = sched.state()
    assert state["tasks"]["boom"]["last_ok"] is False
    assert state["tasks"]["ok"]["last_ok"] is True


async def test_async_task_supported(memory):
    clock = FakeClock()
    sched = Scheduler(memory, time_fn=clock)
    hits = []

    async def coro():
        await asyncio.sleep(0)
        hits.append(1)

    sched.add_task("async", interval=5.0, fn=coro, run_at_start=True)
    await sched.run_due()
    assert hits == [1]


async def test_run_forever_max_ticks(memory):
    clock = FakeClock()
    sched = Scheduler(memory, time_fn=clock)
    n = []
    sched.add_task("t", interval=0.0, fn=lambda: n.append(1), run_at_start=True)
    await sched.run_forever(tick=0.001, max_ticks=3)
    assert len(n) == 3


async def test_build_default_scheduler_wires_four_engines(memory):
    sched = build_default_scheduler(memory)
    state = sched.state()
    assert set(state["tasks"]) == {"curiosity", "janitor", "dreamer", "evolution"}


async def test_build_default_scheduler_adds_session_sync_when_configured(settings):
    from silhouette.daemon import build_default_scheduler
    from silhouette.storage import MemorySystem

    settings.openclaw_agents_dir = settings.data_dir / "agents"
    settings.openclaw_agents_dir.mkdir(parents=True, exist_ok=True)
    mem = MemorySystem(settings)
    sched = build_default_scheduler(mem)
    assert "session_sync" in sched.state()["tasks"]
    mem.close()


async def test_heartbeat_written(memory):
    clock = FakeClock()
    sched = Scheduler(memory, time_fn=clock)
    sched.add_task("t", interval=5.0, fn=lambda: "ok", run_at_start=True)
    await sched.run_due()
    hb = memory.settings.db_path("heartbeat_state.json")
    assert hb.exists()
