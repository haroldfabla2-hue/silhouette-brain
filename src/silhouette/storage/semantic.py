"""Long-term semantic memory: records + embeddings with cosine retrieval.

Embeddings are stored as JSON arrays in SQLite. Search is an exact cosine scan,
which is more than fast enough for tens of thousands of vectors; for larger
corpora a dedicated vector index can be plugged in behind the same interface.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from silhouette.embeddings.base import Embedder, cosine_similarity
from silhouette.models import MemoryRecord, ScoredRecord, Tier
from silhouette.storage._tags import matches_tags, normalize_tags
from silhouette.storage.sqlite import connect, writing

if TYPE_CHECKING:
    from silhouette.storage.ann import ShadowIndex
    from silhouette.storage.ann_persistent import PersistentShadowIndex


class SemanticStore:
    def __init__(self, path: str | Path, embedder: Embedder, *, ann_shadow: bool = False,
                 ann_cache_path: str | Path | None = None, ann_ef: int = 500) -> None:
        self._conn = connect(path)
        self._embedder = embedder
        self._init_schema()
        self._ann_shadow = ann_shadow
        self._ann: ShadowIndex | PersistentShadowIndex | None = None
        self._ann_ef = ann_ef
        self._ann_cache_path = ann_cache_path
        self._path = path
        self._ann_generation: object = None

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
            from silhouette.storage.ann_persistent import install_journal

            install_journal(self._conn)
            # FTS5 is a rebuildable projection. It never replaces canonical vectors.
            self._conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS vectors_fts
                USING fts5(id UNINDEXED, content, tokenize='unicode61')""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS vector_tags (
                id TEXT NOT NULL, tag TEXT NOT NULL,
                PRIMARY KEY (id, tag))""")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_vector_tags_tag ON vector_tags(tag, id)")
        # Rebuild only if the projection is missing rows (legacy database).
        # The vector and lexical writes below share one SQLite transaction.
        vector_count = self.count()
        indexed_count = self._conn.execute("SELECT count(*) FROM vectors_fts").fetchone()[0]
        tag_count = self._conn.execute("SELECT count(*) FROM vector_tags").fetchone()[0]
        has_tags = self._conn.execute("SELECT 1 FROM vectors WHERE tags NOT IN ('[]', '[ ]') LIMIT 1").fetchone()
        if vector_count != indexed_count or (has_tags and not tag_count):
            self.rebuild_lexical_index()

    def rebuild_lexical_index(self) -> None:
        """Idempotently repair old databases or interrupted projection writes."""
        with writing(self._conn):
            self._conn.execute("DELETE FROM vectors_fts")
            self._conn.execute("DELETE FROM vector_tags")
            self._conn.execute("INSERT INTO vectors_fts (id, content) SELECT id, content FROM vectors")
            for row in self._conn.execute("SELECT id, tags FROM vectors"):
                self._conn.executemany("INSERT OR IGNORE INTO vector_tags VALUES (?, ?)",
                    ((row["id"], tag) for tag in normalize_tags(json.loads(row["tags"]))))

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
            self._conn.execute("DELETE FROM vectors_fts WHERE id=?", (record.id,))
            self._conn.execute("INSERT INTO vectors_fts (id, content) VALUES (?, ?)",
                               (record.id, record.content))
            self._conn.execute("DELETE FROM vector_tags WHERE id=?", (record.id,))
            self._conn.executemany("INSERT OR IGNORE INTO vector_tags VALUES (?, ?)",
                ((record.id, tag) for tag in normalize_tags(record.tags)))
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
        # Exact cosine remains the default until ANN passes a measured shadow
        # comparison on real, labeled data. Apply tag filtering in SQLite first.
        if wanted:
            placeholders = ",".join("?" for _ in wanted)
            rows = self._conn.execute(
                f"""SELECT v.* FROM vectors v WHERE EXISTS (
                    SELECT 1 FROM vector_tags t WHERE t.id=v.id
                    AND t.tag IN ({placeholders}))""", tuple(wanted)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM vectors ORDER BY id").fetchall()
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

    def ann_shadow_compare(self, query: str, limit: int = 10) -> dict[str, object]:
        """Explicit diagnostic only. Exact retrieval is never replaced.

        Default shadow indexes rebuild after commits. An explicit ann_cache_path
        enables incremental persistent replay. Exact search remains unchanged.
        """
        from silhouette.storage.ann import ShadowIndex, clock_ms, compare_ids, rerank

        if limit <= 0:
            raise ValueError("limit must be positive")
        if not self._ann_shadow:
            raise RuntimeError("Enable ann_shadow explicitly for diagnostics")
        generation = (self._conn.total_changes,
                      self._conn.execute("PRAGMA data_version").fetchone()[0])
        rebuild_ms = 0.0
        sync_report: dict[str, object] | None = None
        sync_ms = 0.0
        if self._ann_cache_path is not None:
            from silhouette.storage.ann_persistent import PersistentShadowIndex

            if self._ann is None:
                self._ann = PersistentShadowIndex(self._path, self._ann_cache_path,
                    self._embedder.dims, self._embedder.name, ef=self._ann_ef)
            assert isinstance(self._ann, PersistentShadowIndex)
            started = clock_ms()
            sync_report = self._ann.sync()
            sync_ms = clock_ms() - started
            rebuild_ms = sync_ms if sync_report["rebuild"] else 0.0
        elif self._ann is None or generation != self._ann_generation:
            started = clock_ms()
            index = ShadowIndex(self._embedder.dims, ef=self._ann_ef)
            index.rebuild(self._conn.execute("SELECT id, embedding FROM vectors ORDER BY id").fetchall(), generation)
            self._ann, self._ann_generation = index, generation
            rebuild_ms = clock_ms() - started
        started = clock_ms()
        exact = self.search(query, limit=limit)
        exact_ms = clock_ms() - started
        started = clock_ms()
        vector = self._embedder.embed(query)
        ids = self._ann.candidates(vector, max(limit * 5, 50), generation)
        rows = [self._conn.execute("SELECT * FROM vectors WHERE id=?", (item,)).fetchone() for item in ids]
        ranked = rerank([row for row in rows if row is not None], vector, limit)
        ann_ids = [row["id"] for row, _ in ranked]
        ann_ms = clock_ms() - started
        # Detect an external writer during the comparison rather than report stale quality.
        current = (self._conn.total_changes, self._conn.execute("PRAGMA data_version").fetchone()[0])
        if current != generation:
            raise RuntimeError("Corpus changed during shadow comparison; retry")
        exact_ids = [hit.record.id for hit in exact]
        return {"exact_ids": exact_ids, "ann_ids": ann_ids,
                "recall_at_k": compare_ids(exact_ids, ann_ids), "k": limit,
                "exact_ms": exact_ms, "ann_ms": ann_ms, "rebuild_ms": rebuild_ms,
                "corpus_size": self.count(), "embedder": self._embedder.name,
                "sync_ms": sync_ms, "incremental": sync_report}

    def lexical_search(self, query: str, limit: int = 30,
                       tags: Sequence[str] | None = None) -> list[ScoredRecord]:
        """Indexed lexical candidates; FTS5 syntax is never passed through raw."""
        import re

        words = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
        if not words or limit <= 0:
            return []
        expression = " OR ".join('"' + word.replace('"', '""') + '"' for word in words)
        wanted = normalize_tags(tags)
        where = ""
        params: list[object] = [expression]
        if wanted:
            where = f" AND EXISTS (SELECT 1 FROM vector_tags t WHERE t.id=v.id AND t.tag IN ({','.join('?' for _ in wanted)}))"
            params.extend(wanted)
        params.append(limit)
        rows = self._conn.execute(
            f"""SELECT v.*, bm25(vectors_fts) AS rank FROM vectors_fts
                JOIN vectors v ON v.id=vectors_fts.id
                WHERE vectors_fts MATCH ? {where}
                ORDER BY rank, v.id LIMIT ?""", params).fetchall()
        return [ScoredRecord(record=self._row_to_record(row),
                             score=1.0 / (1.0 + max(0.0, row["rank"])),
                             origin="lexical") for row in rows]

    def hybrid_search(self, query: str, limit: int = 5, *,
                      tags: Sequence[str] | None = None,
                      candidate_limit: int = 50) -> list[ScoredRecord]:
        """Fuse exact semantic and FTS5 ranks; a small-corpus, opt-in path.

        ANN cannot be substituted safely until recall and p95 are measured on
        a representative labeled corpus. Score thresholds do not apply to RRF.
        """
        if limit <= 0:
            return []
        size = max(limit, candidate_limit)
        semantic = self.search(query, limit=size, tags=tags)
        lexical = self.lexical_search(query, limit=size, tags=tags)
        ranks: dict[str, float] = {}
        records: dict[str, MemoryRecord] = {}
        for stream in (semantic, lexical):
            for index, hit in enumerate(stream):
                ranks[hit.record.id] = ranks.get(hit.record.id, 0.0) + 1.0 / (60 + index + 1)
                records[hit.record.id] = hit.record
        ids = sorted(ranks, key=lambda record_id: (-ranks[record_id], record_id))[:limit]
        return [ScoredRecord(record=records[record_id], score=ranks[record_id],
                             origin="hybrid") for record_id in ids]

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
            self._conn.execute("DELETE FROM vectors_fts WHERE id = ?", (record_id,))
            self._conn.execute("DELETE FROM vector_tags WHERE id = ?", (record_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0])

    def has_embedding(self, record_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM vectors WHERE id = ?", (record_id,)
        ).fetchone()
        return row is not None

    def matches(self, record: MemoryRecord) -> bool:
        """Read back the persisted projection, not just an in-memory success."""
        row = self._conn.execute("SELECT content, tags, source, importance, created_at FROM vectors WHERE id=?",
                                 (record.id,)).fetchone()
        return row is not None and (row["content"], json.loads(row["tags"]),
            row["source"], row["importance"], row["created_at"]) == (
            record.content, record.tags, record.source, record.importance, record.created_at)

    def close(self) -> None:
        self._conn.close()
