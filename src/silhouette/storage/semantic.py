"""Long-term semantic memory: records + embeddings with cosine retrieval.

Embeddings are stored as JSON arrays in SQLite. Search is an exact cosine scan,
which is more than fast enough for tens of thousands of vectors; for larger
corpora a dedicated vector index can be plugged in behind the same interface.
"""

from __future__ import annotations

from collections.abc import Sequence

import json
import sqlite3
from pathlib import Path

from silhouette.embeddings.base import Embedder, cosine_similarity
from silhouette.models import MemoryRecord, ScoredRecord, Tier
from silhouette.storage.sqlite import connect, writing
from silhouette.storage._tags import matches_tags, normalize_tags


class SemanticStore:
    def __init__(self, path: str | Path, embedder: Embedder) -> None:
        self._conn = connect(path)
        self._embedder = embedder
        self._init_schema()

    def _init_schema(self) -> None:
        with writing(self._conn):
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vectors (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    source TEXT NOT NULL,
                    importance REAL NOT NULL,
                    created_at REAL NOT NULL,
                    embedding TEXT NOT NULL
                )
                """
            )

    def add(self, record: MemoryRecord) -> MemoryRecord:
        embedding = record.embedding or self._embedder.embed(record.content)
        record.embedding = embedding
        with writing(self._conn):
            self._conn.execute(
                """
                INSERT OR REPLACE INTO vectors
                (id, content, tags, source, importance, created_at, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.content,
                    json.dumps(record.tags),
                    record.source,
                    record.importance,
                    record.created_at,
                    json.dumps(embedding),
                ),
            )
        return record

    def search(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.0,
        tags: Sequence[str] | None = None,
    ) -> list[ScoredRecord]:
        wanted = normalize_tags(tags)
        query_vec = self._embedder.embed(query)
        rows = self._conn.execute("SELECT * FROM vectors").fetchall()
        scored: list[ScoredRecord] = []
        for row in rows:
            vec = json.loads(row["embedding"])
            score = cosine_similarity(query_vec, vec)
            if score < min_score:
                continue
            if wanted and not matches_tags(json.loads(row["tags"]), wanted):
                continue
            scored.append(
                ScoredRecord(
                    record=self._row_to_record(row),
                    score=score,
                    origin="semantic",
                )
            )
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            content=row["content"],
            tier=Tier.SEMANTIC,
            importance=row["importance"],
            tags=json.loads(row["tags"]),
            source=row["source"],
            created_at=row["created_at"],
            embedding=json.loads(row["embedding"]),
        )

    def delete(self, record_id: str) -> bool:
        with writing(self._conn):
            cur = self._conn.execute("DELETE FROM vectors WHERE id = ?", (record_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0])

    def has_embedding(self, record_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM vectors WHERE id = ?", (record_id,)
        ).fetchone()
        return row is not None

    def close(self) -> None:
        self._conn.close()
