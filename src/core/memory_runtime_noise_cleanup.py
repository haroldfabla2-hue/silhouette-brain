import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
import os
#!/usr/bin/env python3
"""
One-shot cleanup utility to purge runtime operational noise from memory stores.

It creates backups before changing data and is safe to run multiple times.
"""
import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from memory_noise_filter import is_operational_runtime_noise

DATA_DIR = Path(os.getenv("BRAIN_DATA_DIR", "./data"))
DB_PATH = DATA_DIR / "memory_core.db"
PRIORITY_PATH = DATA_DIR / "priority_memory.json"
BACKUP_ROOT = DATA_DIR / "backups"


def _chunked(items: List[str], size: int = 500) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def create_backups() -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_ROOT / f"runtime-noise-cleanup-{ts}"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DB_PATH, target / DB_PATH.name)
    shutil.copy2(PRIORITY_PATH, target / PRIORITY_PATH.name)
    return target


def cleanup_db(dry_run: bool = False) -> Dict[str, int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, message FROM conversations")
    rows = cur.fetchall()

    noisy_ids = [row[0] for row in rows if is_operational_runtime_noise(row[1] or "")]
    removed = len(noisy_ids)

    if not dry_run and noisy_ids:
        for chunk in _chunked(noisy_ids):
            placeholders = ",".join("?" * len(chunk))
            cur.execute(f"DELETE FROM conversations WHERE id IN ({placeholders})", chunk)
            try:
                cur.execute(f"DELETE FROM embeddings WHERE message_id IN ({placeholders})", chunk)
            except sqlite3.OperationalError:
                pass
        conn.commit()

    cur.execute("SELECT COUNT(*) FROM conversations")
    remaining = int(cur.fetchone()[0])
    conn.close()
    return {"removed": removed, "remaining": remaining}


def cleanup_priority_memory(dry_run: bool = False) -> Dict[str, int]:
    with PRIORITY_PATH.open() as fp:
        data = json.load(fp)

    never_forget = data.get("never_forget", [])
    important = data.get("important", [])
    recurring = data.get("recurring", {})

    filtered_never_forget = [
        item for item in never_forget
        if not is_operational_runtime_noise(item.get("content", ""))
    ]
    filtered_important = [
        item for item in important
        if not is_operational_runtime_noise(item.get("content", ""))
    ]

    removed_recurring = [
        key for key in list(recurring.keys())
        if is_operational_runtime_noise(key)
    ]
    for key in removed_recurring:
        recurring.pop(key, None)

    removed_nf = len(never_forget) - len(filtered_never_forget)
    removed_imp = len(important) - len(filtered_important)

    changed = removed_nf > 0 or removed_imp > 0 or len(removed_recurring) > 0
    if changed and not dry_run:
        data["never_forget"] = filtered_never_forget
        data["important"] = filtered_important
        data["recurring"] = recurring
        with PRIORITY_PATH.open("w") as fp:
            json.dump(data, fp, indent=2)

    return {
        "removed_never_forget": removed_nf,
        "removed_important": removed_imp,
        "removed_recurring_keys": len(removed_recurring),
        "remaining_never_forget": len(filtered_never_forget),
        "remaining_important": len(filtered_important),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Analyze only; do not write changes.")
    args = parser.parse_args()

    backup_dir = None
    if not args.dry_run:
        backup_dir = create_backups()

    db_stats = cleanup_db(dry_run=args.dry_run)
    priority_stats = cleanup_priority_memory(dry_run=args.dry_run)

    report = {
        "dry_run": args.dry_run,
        "backup_dir": str(backup_dir) if backup_dir else None,
        "db": db_stats,
        "priority_memory": priority_stats,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
