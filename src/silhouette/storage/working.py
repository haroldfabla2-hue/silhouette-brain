"""Working memory: ultra-fast, ephemeral, bounded recency cache.

In-memory by default (an LRU map with TTL). If a Redis URL is configured and
the ``redis`` package is installed, recent records are also mirrored there so
they survive process restarts and can be shared across workers.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

from silhouette.config import Settings, get_settings
from silhouette.models import MemoryRecord

logger = logging.getLogger("silhouette.storage.working")


class WorkingMemory:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._capacity = max(1, self._settings.working_capacity)
        self._ttl = self._settings.working_ttl_seconds
        self._items: OrderedDict[str, MemoryRecord] = OrderedDict()
        self._redis = self._maybe_connect_redis()

    def _maybe_connect_redis(self):  # pragma: no cover - optional dependency
        if not self._settings.redis_url:
            return None
        try:
            import redis

            client = redis.Redis.from_url(self._settings.redis_url)
            client.ping()
            logger.info("Working memory mirroring to Redis")
            return client
        except Exception as exc:
            logger.warning("Redis unavailable (%s); using in-memory working memory", exc)
            return None

    def _evict(self) -> None:
        now = time.time()
        if self._ttl > 0:
            expired = [k for k, v in self._items.items() if now - v.created_at > self._ttl]
            for k in expired:
                self._items.pop(k, None)
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)

    def put(self, record: MemoryRecord) -> None:
        self._items[record.id] = record
        self._items.move_to_end(record.id)
        self._evict()
        if self._redis is not None:  # pragma: no cover - optional dependency
            try:
                key = f"silhouette:working:{record.id}"
                self._redis.set(key, record.model_dump_json(), ex=self._ttl or None)
            except Exception as exc:
                logger.debug("Redis put failed: %s", exc)

    def get(self, record_id: str) -> MemoryRecord | None:
        record = self._items.get(record_id)
        if record is not None:
            self._items.move_to_end(record_id)
            record.touch()
        return record

    def recent(self, limit: int = 20) -> list[MemoryRecord]:
        self._evict()
        records = list(self._items.values())
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    def __len__(self) -> int:
        self._evict()
        return len(self._items)

    def discard(self, record_id: str) -> bool:
        """Drop one record from the buffer. True when it was there."""
        existed = self._items.pop(record_id, None) is not None
        if self._redis is not None:  # pragma: no cover - optional dependency
            try:
                self._redis.delete(f"silhouette:working:{record_id}")
            except Exception as exc:
                logger.debug("Redis delete failed: %s", exc)
        return existed

    def clear(self) -> None:
        self._items.clear()
