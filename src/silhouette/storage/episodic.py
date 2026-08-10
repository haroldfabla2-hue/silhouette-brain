"""Episodic memory: recent, durable episodes stored in SQLite."""

from __future__ import annotations

from collections.abc import Sequence

import json
import sqlite3
import time
from pathlib import Path

from silhouette.models import MemoryRecord, Tier
from silhouette.storage.sqlite import connect, writing
from silhouette.storage._tags import matches_tags, normalize_tags


class EpisodicStore:
    def __init__(self, path: str | Path) -> None:
        self._conn = connect(path)
        self._init_schema()

    def _init_schema(self) -> None:
        with writing(self._conn):
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    importance REAL NOT NULL,
                    tags TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_access REAL NOT NULL,
                    access_count INTEGER NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at)"
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            content=row["content"],
            tier=Tier(row["tier"]),
            importance=row["importance"],
            tags=json.loads(row["tags"]),
            source=row["source"],
            created_at=row["created_at"],
            last_access=row["last_access"],
            access_count=row["access_count"],
            metadata=json.loads(row["metadata"]),
        )

    def add(self, record: MemoryRecord) -> None:
        with writing(self._conn):
            self._conn.execute(
                """
                INSERT OR REPLACE INTO episodes
                (id, content, tier, importance, tags, source, created_at,
                 last_access, access_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.content,
                    record.tier.value,
                    record.importance,
                    json.dumps(record.tags),
                    record.source,
                    record.created_at,
                    record.last_access,
                    record.access_count,
                    json.dumps(record.metadata, default=str),
                ),
            )

    def recent(
        self,
        hours: float = 24.0,
        limit: int = 20,
        tags: Sequence[str] | None = None,
    ) -> list[MemoryRecord]:
        cutoff = time.time() - hours * 3600.0
        wanted = normalize_tags(tags)
        if not wanted:
            rows = self._conn.execute(
                "SELECT * FROM episodes WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        # Con filtro se recorre en orden y se corta al llegar al limite: el
        # limite debe contar registros VISIBLES, no leidos.
        rows = self._conn.execute(
            "SELECT * FROM episodes WHERE created_at >= ? ORDER BY created_at DESC",
            (cutoff,),
        ).fetchall()
        salida: list[MemoryRecord] = []
        for row in rows:
            if not matches_tags(json.loads(row["tags"]), wanted):
                continue
            salida.append(self._row_to_record(row))
            if len(salida) >= limit:
                break
        return salida

    def all(self, limit: int = 1000) -> list[MemoryRecord]:
        rows = self._conn.execute(
            "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get(self, record_id: str) -> MemoryRecord | None:
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE id = ?", (record_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def delete(self, record_id: str) -> bool:
        with writing(self._conn):
            cur = self._conn.execute("DELETE FROM episodes WHERE id = ?", (record_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0])

    def close(self) -> None:
        self._conn.close()
