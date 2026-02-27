import os
#!/usr/bin/env python3
"""
Incrementally sync Silhouette OpenClaw session messages into memory_core.db.

Default behavior is safe bootstrap:
- First run records EOF offsets for existing files and does not backfill history.
- Next runs only ingest newly appended lines.

Use --backfill once if you want to import full existing history.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Tuple

import sys

sys.path.insert(0, "/root/.openclaw/skills/silhouette-memory/scripts")
from memory_core import get_memory_core  # noqa: E402


SESSIONS_DIR = Path("/root/.openclaw/agents/silhouette/sessions")
STATE_PATH = Path(os.getenv("BRAIN_DATA_DIR", "./data"/session_sync_state.json")
VALID_ROLES = {"user", "assistant"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> Dict:
    if not STATE_PATH.exists():
        return {"version": 1, "createdAt": _now_iso(), "offsets": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        # If state becomes corrupt, start fresh without crashing the sync loop.
        return {"version": 1, "createdAt": _now_iso(), "offsets": {}}


def save_state(state: Dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def iter_session_files() -> Iterable[Path]:
    return sorted(
        p
        for p in SESSIONS_DIR.glob("*.jsonl")
        if ".deleted." not in p.name and ".reset." not in p.name
    )


def extract_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        text = ""
        if kind == "text":
            text = item.get("text") or ""
        elif kind in {"input_text", "output_text"}:
            text = item.get("text") or item.get("value") or ""
        if isinstance(text, str):
            text = text.strip()
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def process_file(path: Path, start_offset: int, core) -> Tuple[int, Dict[str, int]]:
    stats = {"inserted": 0, "skipped": 0, "errors": 0}
    size = path.stat().st_size

    # File rotated/recreated; restart from beginning.
    if start_offset > size:
        start_offset = 0

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(start_offset)
        for raw in fh:
            line = raw.strip()
            if not line:
                stats["skipped"] += 1
                continue
            try:
                rec = json.loads(line)
            except Exception:
                stats["errors"] += 1
                continue

            if rec.get("type") != "message":
                stats["skipped"] += 1
                continue

            msg = rec.get("message") or {}
            role = msg.get("role")
            if role not in VALID_ROLES:
                stats["skipped"] += 1
                continue

            text = extract_text(msg.get("content"))
            if not text:
                stats["skipped"] += 1
                continue

            session_id = path.stem
            tags = ["openclaw-sync", f"role:{role}", f"session:{session_id}"]
            try:
                core.store_message(
                    role,
                    text,
                    context=f"openclaw-session:{session_id}",
                    tags=tags,
                )
                stats["inserted"] += 1
            except Exception:
                stats["errors"] += 1

        end_offset = fh.tell()

    return end_offset, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="On first run, import full existing history instead of bootstrapping at EOF.",
    )
    args = parser.parse_args()

    files = list(iter_session_files())
    state = load_state()
    offsets = state.setdefault("offsets", {})
    mtimes = state.setdefault("mtimes", {})
    core = get_memory_core()

    # Remove offsets for files that no longer exist.
    valid = {str(p) for p in files}
    for key in list(offsets):
        if key not in valid:
            offsets.pop(key, None)
    for key in list(mtimes):
        if key not in valid:
            mtimes.pop(key, None)

    summary = {
        "files": len(files),
        "bootstrapped": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
    }

    for path in files:
        key = str(path)
        mtime = path.stat().st_mtime
        if key not in offsets and not args.backfill:
            offsets[key] = path.stat().st_size
            mtimes[key] = mtime
            summary["bootstrapped"] += 1
            continue

        if key in offsets and mtimes.get(key) == mtime:
            continue

        start = int(offsets.get(key, 0))
        end, stats = process_file(path, start, core)
        offsets[key] = end
        mtimes[key] = mtime
        summary["inserted"] += stats["inserted"]
        summary["skipped"] += stats["skipped"]
        summary["errors"] += stats["errors"]

    state["updatedAt"] = _now_iso()
    save_state(state)

    print(
        "sync_openclaw_sessions:",
        f"files={summary['files']}",
        f"bootstrapped={summary['bootstrapped']}",
        f"inserted={summary['inserted']}",
        f"skipped={summary['skipped']}",
        f"errors={summary['errors']}",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
