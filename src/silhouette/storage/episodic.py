"""Episodic memory: recent, durable episodes stored in SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path

from silhouette.models import MemoryRecord, Tier
from silhouette.storage._tags import matches_tags, normalize_tags
from silhouette.storage.sqlite import connect, writing


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
            columns = {row[1] for row in self._conn.execute("PRAGMA table_info(episodes)")}
            if "deleted" not in columns:
                self._conn.execute("ALTER TABLE episodes ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at)"
            )
            self._conn.execute("""CREATE TABLE IF NOT EXISTS projection_outbox (
                id TEXT PRIMARY KEY, version TEXT NOT NULL,
                operation TEXT NOT NULL, link_entities INTEGER NOT NULL,
                semantic_done INTEGER NOT NULL DEFAULT 0,
                graph_done INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            )""")

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

    @staticmethod
    def version(record: MemoryRecord) -> str:
        """Stable fingerprint of the inputs that produce the projections."""
        payload = json.dumps([record.content, record.tags, record.source,
                              record.importance, record.created_at], sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def queue(self, record: MemoryRecord, *, link_entities: bool = True) -> None:
        """Commit the canonical episode and its projection intent together."""
        version = self.version(record)
        with writing(self._conn):
            old = self._conn.execute("SELECT * FROM episodes WHERE id=?", (record.id,)).fetchone()
            if old is not None and self.version(self._row_to_record(old)) != version:
                raise ValueError("An episode ID cannot be reused for different content")
            if old is not None and old["deleted"]:
                raise ValueError("Cannot reuse a tombstoned episode ID")
            self._insert(record)
            self._conn.execute("""INSERT INTO projection_outbox
                (id, version, operation, link_entities, updated_at)
                VALUES (?, ?, 'upsert', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                version=excluded.version, operation='upsert',
                link_entities=excluded.link_entities, semantic_done=0,
                graph_done=0, updated_at=excluded.updated_at""",
                (record.id, version, int(link_entities), time.time()))

    def _insert(self, record: MemoryRecord) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO episodes
            (id, content, tier, importance, tags, source, created_at,
             last_access, access_count, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.id, record.content, record.tier.value, record.importance,
             json.dumps(record.tags), record.source, record.created_at,
             record.last_access, record.access_count,
             json.dumps(record.metadata, default=str)))

    def pending(self) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM projection_outbox ORDER BY updated_at, id").fetchall()

    def mark_done(self, record_id: str, version: str, operation: str, tier: str) -> None:
        if tier not in ("semantic", "graph"):
            raise ValueError("Unknown projection tier")
        with writing(self._conn):
            self._conn.execute(
                f"UPDATE projection_outbox SET {tier}_done=1 WHERE id=? AND version=? AND operation=?",
                (record_id, version, operation))
            complete = self._conn.execute("""SELECT 1 FROM projection_outbox WHERE id=?
                AND semantic_done=1 AND graph_done=1""", (record_id,)).fetchone()
            if complete:
                if operation == "delete":
                    self._conn.execute("DELETE FROM episodes WHERE id=? AND deleted=1", (record_id,))
                self._conn.execute("DELETE FROM projection_outbox WHERE id=?", (record_id,))

    def tombstone(self, record_id: str) -> bool:
        """Remove source visibility and queue a durable retraction atomically."""
        with writing(self._conn):
            row = self._conn.execute("SELECT 1 FROM episodes WHERE id=? AND deleted=0", (record_id,)).fetchone()
            if row is None:
                return False
            self._conn.execute("UPDATE episodes SET deleted=1 WHERE id=?", (record_id,))
            self._conn.execute("""INSERT INTO projection_outbox
                (id, version, operation, link_entities, updated_at)
                VALUES (?, ?, 'delete', 0, ?)
                ON CONFLICT(id) DO UPDATE SET operation='delete',
                semantic_done=0, graph_done=0, updated_at=excluded.updated_at""",
                (record_id, 'tombstone', time.time()))
        return True

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
                "SELECT * FROM episodes WHERE deleted=0 AND created_at >= ? ORDER BY created_at DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        # Con filtro se recorre en orden y se corta al llegar al limite: el
        # limite debe contar registros VISIBLES, no leidos.
        rows = self._conn.execute(
            "SELECT * FROM episodes WHERE deleted=0 AND created_at >= ? ORDER BY created_at DESC",
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
            "SELECT * FROM episodes WHERE deleted=0 ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get(self, record_id: str) -> MemoryRecord | None:
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE id = ? AND deleted=0", (record_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def delete(self, record_id: str) -> bool:
        with writing(self._conn):
            cur = self._conn.execute("DELETE FROM episodes WHERE id = ?", (record_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM episodes WHERE deleted=0").fetchone()[0])

    def close(self) -> None:
        self._conn.close()
