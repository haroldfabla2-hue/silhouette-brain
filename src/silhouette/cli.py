"""Command-line interface: ``silhouette <command>``.

Commands
--------
serve     Run the HTTP API (FastAPI + uvicorn).
daemon    Run the cognitive daemon (Curiosity/Janitor/Dreamer/Evolution).
remember  Store a memory.
query     Semantic recall.
context   Assemble a context packet for a query.
engine    Run a single engine once.
stats     Print memory statistics.
"""

from __future__ import annotations

import argparse
import json
import sys

from silhouette import __version__
from silhouette.config import get_settings
from silhouette.storage.memory import MemorySystem


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str, ensure_ascii=False))


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from silhouette.api import create_app

    settings = get_settings()
    app = create_app()
    uvicorn.run(app, host=args.host or settings.api_host, port=args.port or settings.api_port)
    return 0


def cmd_daemon(_: argparse.Namespace) -> int:
    from silhouette.daemon.runner import main as daemon_main

    daemon_main()
    return 0


def cmd_remember(args: argparse.Namespace) -> int:
    mem = MemorySystem()
    rec = mem.remember(args.content, importance=args.importance, tags=args.tags or [])
    _print({"id": rec.id, "status": "ok"})
    mem.close()
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    mem = MemorySystem()
    results = mem.recall(args.query, limit=args.limit, min_score=args.min_score)
    _print([{"score": round(r.score, 4), "content": r.record.content} for r in results])
    mem.close()
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    from silhouette.reasoning import ContextAssembler, get_synthesizer

    mem = MemorySystem()
    asm = ContextAssembler(mem, get_synthesizer(mem.settings))
    packet = asm.assemble(args.query, include_graph=args.graph, synthesize=args.synthesize)
    _print(packet.model_dump())
    mem.close()
    return 0


def cmd_engine(args: argparse.Namespace) -> int:
    from silhouette.engines import DEFAULT_ENGINES

    engine = DEFAULT_ENGINES.get(args.name)
    if engine is None:
        print(f"Unknown engine '{args.name}'. Choices: {', '.join(DEFAULT_ENGINES)}", file=sys.stderr)
        return 2
    mem = MemorySystem()
    result = engine.run(mem)
    _print(result.model_dump())
    mem.close()
    return 0


def cmd_stats(_: argparse.Namespace) -> int:
    mem = MemorySystem()
    _print(mem.stats())
    mem.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="silhouette", description="Silhouette Brain CLI")
    parser.add_argument("--version", action="version", version=f"silhouette {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="Run the HTTP API")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("daemon", help="Run the cognitive daemon")
    p.set_defaults(func=cmd_daemon)

    p = sub.add_parser("remember", help="Store a memory")
    p.add_argument("content")
    p.add_argument("--importance", type=float, default=0.5)
    p.add_argument("--tags", nargs="*")
    p.set_defaults(func=cmd_remember)

    p = sub.add_parser("query", help="Semantic recall")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--min-score", dest="min_score", type=float, default=0.0)
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("context", help="Assemble a context packet")
    p.add_argument("query")
    p.add_argument("--graph", action="store_true")
    p.add_argument("--synthesize", action="store_true")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("engine", help="Run one engine once")
    p.add_argument("name")
    p.set_defaults(func=cmd_engine)

    p = sub.add_parser("stats", help="Print memory statistics")
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
