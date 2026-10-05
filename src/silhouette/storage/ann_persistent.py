"""Opt-in incremental HNSW cache. SQLite vectors remain authoritative.

The cache must be private, trusted local storage, not an uploaded artifact.
Journal retention/compaction and provider migrations are deliberately not automatic.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any


def install_journal(conn: sqlite3.Connection) -> None:
    """Triggers cover other connections and direct SQL, including REPLACE."""
    conn.execute("CREATE TABLE IF NOT EXISTS ann_source (identity TEXT NOT NULL)")
    if conn.execute("SELECT 1 FROM ann_source").fetchone() is None:
        conn.execute("INSERT INTO ann_source VALUES (?)", (str(uuid.uuid4()),))
    conn.execute("""CREATE TABLE IF NOT EXISTS ann_changes (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL)""")
    for operation in ("INSERT", "UPDATE", "DELETE"):
        row = "OLD" if operation == "DELETE" else "NEW"
        conn.execute(f"""CREATE TRIGGER IF NOT EXISTS ann_{operation.lower()}
            AFTER {operation} ON vectors BEGIN
            INSERT INTO ann_changes(id) VALUES ({row}.id); END""")
    # Updating an id must remove the old label as well as add the new one.
    conn.execute("""CREATE TRIGGER IF NOT EXISTS ann_rename AFTER UPDATE OF id ON vectors
        WHEN OLD.id != NEW.id BEGIN INSERT INTO ann_changes(id) VALUES (OLD.id); END""")


class PersistentShadowIndex:
    """One cache per corpus/provider; concurrent cache writes may replay extra work.

    A cache checkpoint never advances until index bytes and metadata commit together.
    An interrupted update leaves the previous checkpoint or a recoverable cache miss.
    """

    def __init__(self, source: str | Path, cache: str | Path, dims: int,
                 provider: str, *, ef: int = 100) -> None:
        import hnswlib

        self.source, self.cache = Path(source), Path(cache)
        if self.source.resolve() == self.cache.resolve():
            raise ValueError("ANN cache must not overwrite the canonical database")
        self.dims, self.provider, self.ef = dims, provider, ef
        self._backend = hnswlib
        self._lock = threading.RLock()
        self._index: Any = None
        self._labels: dict[str, int] = {}
        self._active: set[str] = set()
        self._reverse: dict[int, str] = {}
        self._seq = -1
        self._identity = ""
        self._loaded = False
        self._capacity = 1

    def _key(self, identity: str) -> str:
        return json.dumps([identity, self.provider, self.dims], separators=(",", ":"))

    def _new(self) -> None:
        self._index = self._backend.Index(space="cosine", dim=self.dims)
        self._index.init_index(max_elements=1, ef_construction=200, M=16, random_seed=17)
        self._index.set_num_threads(1)
        self._index.set_ef(max(self.ef, 10))
        self._labels, self._active, self._capacity = {}, set(), 1
        self._reverse = {}

    def _restore(self, identity: str) -> bool:
        if not self.cache.exists():
            return False
        try:
            with sqlite3.connect(self.cache) as db:
                row = db.execute("SELECT meta, payload, digest FROM checkpoint WHERE key=1").fetchone()
            if row is None:
                return False
            meta_text, payload, digest = row
            if hashlib.sha256(meta_text.encode() + payload).hexdigest() != digest:
                return False
            meta = json.loads(meta_text)
            if meta["key"] != self._key(identity):
                return False
            labels, active = meta["labels"], set(meta["active"])
            if (not isinstance(meta["seq"], int) or meta["seq"] < 0
                    or not active <= labels.keys()
                    or sorted(labels.values()) != list(range(len(labels)))):
                return False
            index = self._backend.Index(space="cosine", dim=self.dims)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "index.bin"
                path.write_bytes(payload)
                index.load_index(str(path))
            if index.get_current_count() != len(labels):
                return False
            self._index, self._labels, self._active = index, labels, active
            self._reverse = {label: record_id for record_id, label in labels.items()}
            self._capacity, self._seq = index.get_max_elements(), meta["seq"]
            index.set_num_threads(1)
            index.set_ef(max(self.ef, 10))
            return True
        except (sqlite3.Error, ValueError, KeyError, TypeError, RuntimeError):
            return False

    def _save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.bin"
            self._index.save_index(str(path))
            payload = path.read_bytes()
        meta = json.dumps({"key": self._key(self._identity), "seq": self._seq,
                           "labels": self._labels, "active": sorted(self._active)}, sort_keys=True)
        digest = hashlib.sha256(meta.encode() + payload).hexdigest()
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.cache) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS checkpoint
                (key INTEGER PRIMARY KEY, meta TEXT, payload BLOB, digest TEXT)""")
            db.execute("INSERT OR REPLACE INTO checkpoint VALUES (1, ?, ?, ?)",
                       (meta, payload, digest))

    def sync(self) -> dict[str, object]:
        """Read a consistent canonical snapshot, then apply only changed ids."""
        with self._lock, sqlite3.connect(self.source) as source:
            source.row_factory = sqlite3.Row
            source.execute("BEGIN")
            identity = source.execute("SELECT identity FROM ann_source").fetchone()[0]
            seq = source.execute("SELECT coalesce(max(seq), 0) FROM ann_changes").fetchone()[0]
            restored = False
            if not self._loaded or identity != self._identity:
                restored = self._restore(identity)
                self._loaded, self._identity = True, identity
                if not restored:
                    self._seq = -1
            rebuild = self._index is None or self._seq < 0 or self._seq > seq
            if rebuild:
                rows = source.execute("SELECT id, embedding FROM vectors ORDER BY id").fetchall()
                changes = {row["id"]: json.loads(row["embedding"]) for row in rows}
            else:
                ids = source.execute("SELECT DISTINCT id FROM ann_changes WHERE seq > ?",
                                     (self._seq,)).fetchall()
                changes = {}
                for row in ids:
                    vector = source.execute("SELECT embedding FROM vectors WHERE id=?",
                                            (row["id"],)).fetchone()
                    changes[row["id"]] = json.loads(vector[0]) if vector else None
            source.commit()
            for vector in changes.values():
                if vector is not None and (len(vector) != self.dims
                        or not all(math.isfinite(x) for x in vector) or not any(vector)):
                    raise ValueError("ANN requires finite, nonzero, dimension-matched vectors")
            old_seq = self._seq
            try:
                if rebuild:
                    self._new()
                for record_id, vector in changes.items():
                    if vector is None:
                        if record_id in self._active:
                            self._index.mark_deleted(self._labels[record_id])
                            self._active.remove(record_id)
                        continue
                    if record_id not in self._labels:
                        self._labels[record_id] = len(self._labels)
                        self._reverse[self._labels[record_id]] = record_id
                        if len(self._labels) > self._capacity:
                            self._capacity = max(len(self._labels), self._capacity * 2)
                            self._index.resize_index(self._capacity)
                    elif record_id not in self._active:
                        self._index.unmark_deleted(self._labels[record_id])
                    self._index.add_items([vector], [self._labels[record_id]])
                    self._active.add(record_id)
                self._seq = seq
                if rebuild or old_seq != seq:
                    self._save()
            except Exception:
                # Never reuse a partially changed graph or a checkpoint not persisted.
                self._index, self._seq, self._loaded = None, -1, False
                raise
            return {"rebuild": rebuild, "restored": restored, "changed_ids": len(changes),
                    "checkpoint": seq, "active_count": len(self._active)}

    def candidates(self, vector: list[float], limit: int, generation: object = None) -> list[str]:
        with self._lock:
            if self._index is None:
                raise RuntimeError("Sync ANN before querying")
            if len(vector) != self.dims or not all(math.isfinite(x) for x in vector):
                raise ValueError("Invalid query vector")
            if limit <= 0 or not any(vector) or not self._active:
                return []
            k = min(limit, len(self._active))
            self._index.set_ef(max(self.ef, k))
            labels, _ = self._index.knn_query([vector], k=k, num_threads=1)
            return [self._reverse[int(label)] for label in labels[0]]
