"""Entry point that runs the cognitive daemon until interrupted."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from silhouette.daemon.scheduler import build_default_scheduler
from silhouette.storage.memory import MemorySystem


async def _run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    memory = MemorySystem()
    scheduler = build_default_scheduler(memory)
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # add_signal_handler is unavailable on some platforms (e.g. Windows).
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    try:
        await scheduler.run_forever(tick=5.0, stop_event=stop)
    finally:
        memory.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    main()
