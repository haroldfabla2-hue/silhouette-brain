"""Rebuildable HNSW shadow projection. Never a canonical store or default search."""
from __future__ import annotations

import math
import sqlite3
import threading
import time
from typing import Any

from silhouette.embeddings.base import cosine_similarity


class ShadowIndex:
    def __init__(self, dims: int, *, ef: int = 100) -> None:
        import hnswlib

        self._backend = hnswlib
        self.dims = dims
        self.ef = ef
        self._lock = threading.RLock()
        self._index: Any = None
        self._ids: list[str] = []
        self._generation: object = None

    def rebuild(self, rows: list[sqlite3.Row], generation: object) -> None:
        """Build privately then swap atomically; bad vectors fail closed."""
        import json

        import numpy as np

        ids = [row['id'] for row in rows]
        vectors = [json.loads(row['embedding']) for row in rows]
        if any(len(v) != self.dims or not all(math.isfinite(x) for x in v)
               or not any(v) for v in vectors):
            raise ValueError('ANN requires finite, nonzero, dimension-matched vectors')
        index = self._backend.Index(space='cosine', dim=self.dims)
        index.init_index(max_elements=max(1, len(ids)), ef_construction=200, M=16,
                         random_seed=17)
        index.set_num_threads(1)
        index.set_ef(max(self.ef, 10))
        if vectors:
            index.add_items(np.asarray(vectors, dtype=np.float32), np.arange(len(ids)))
        with self._lock:
            self._ids, self._index, self._generation = ids, index, generation

    def candidates(self, vector: list[float], limit: int, generation: object) -> list[str]:
        with self._lock:
            if generation != self._generation:
                raise RuntimeError('Stale ANN projection')
            if len(vector) != self.dims or not all(math.isfinite(x) for x in vector):
                raise ValueError('Invalid query vector')
            if not any(vector) or limit <= 0 or not self._ids:
                return []
            k = min(limit, len(self._ids))
            self._index.set_ef(max(self.ef, k))
            labels, _ = self._index.knn_query([vector], k=k, num_threads=1)
            return [self._ids[int(label)] for label in labels[0]]


def compare_ids(exact: list[str], approximate: list[str]) -> float:
    return len(set(exact) & set(approximate)) / len(exact) if exact else 1.0


def rerank(rows: list[sqlite3.Row], vector: list[float], limit: int) -> list[tuple[sqlite3.Row, float]]:
    import json

    scored = [(row, cosine_similarity(vector, json.loads(row['embedding']))) for row in rows]
    scored.sort(key=lambda item: (-item[1], item[0]['id']))
    return scored[:limit]


def clock_ms() -> float:
    return time.perf_counter() * 1000
