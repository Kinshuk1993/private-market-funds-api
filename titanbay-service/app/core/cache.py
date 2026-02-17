"""
In-memory cache with TTL (time-to-live) expiration.

Implements a lightweight, async-safe cache suitable for reducing database
round-trips on read-heavy endpoints (``GET /funds``, ``GET /investors``).

Design decisions:
- **No external dependency** — Uses a simple dict + TTL approach instead of
  Redis, keeping the zero-dependency testing story intact.  In a production
  deployment at scale, this would be swapped for Redis/Memcached via the
  same interface.
- **Write-through invalidation** — Cache is invalidated on any write operation
  (POST, PUT, DELETE) so stale data is never served.
- **TTL-based expiry** — Entries expire after a configurable number of seconds,
  bounding the staleness window even if invalidation is missed.
- **Max-size eviction** — When the cache exceeds ``max_size`` entries, the
  oldest entry is evicted (FIFO) to prevent unbounded memory growth.

Thread safety:
    Python's GIL + async single-threaded event loop make dict operations
    atomic for our use case.  No additional locking is needed.
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheEntry:
    """A single cached value with creation timestamp."""

    __slots__ = ("value", "created_at")

    def __init__(self, value: Any):
        self.value = value
        self.created_at = time.monotonic()

    def is_expired(self, ttl: float) -> bool:
        """Return True if this entry is older than ``ttl`` seconds."""
        return (time.monotonic() - self.created_at) > ttl


class TTLCache:
    """
    Simple in-memory cache with TTL expiration and max-size eviction.

    Parameters
    ----------
    ttl : float
        Time-to-live in seconds for each cache entry.
    max_size : int
        Maximum number of entries. When exceeded, the oldest entry is evicted.
    enabled : bool
        When False, all operations are no-ops (useful for testing).
    """

    def __init__(
        self,
        ttl: float = 30.0,
        max_size: int = 1000,
        enabled: bool = True,
    ):
        self._store: Dict[str, CacheEntry] = {}
        self._ttl = ttl
        self._max_size = max_size
        self._enabled = enabled
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value by key.

        Returns ``None`` on miss or expired entry.
        """
        if not self._enabled:
            return None

        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired(self._ttl):
            del self._store[key]
            self._misses += 1
            logger.debug("Cache EXPIRED: %s", key)
            return None

        self._hits += 1
        logger.debug("Cache HIT: %s", key)
        return entry.value

    def set(self, key: str, value: Any) -> None:
        """
        Store a value in the cache.

        If the cache is full, the oldest entry is evicted first.
        """
        if not self._enabled:
            return

        # Evict oldest if at capacity
        if len(self._store) >= self._max_size and key not in self._store:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
            logger.debug("Cache EVICTED (max_size): %s", oldest_key)

        self._store[key] = CacheEntry(value)
        logger.debug("Cache SET: %s", key)

    def invalidate(self, *prefixes: str) -> int:
        """
        Remove all entries whose keys start with any of the given prefixes.

        Returns the number of evicted entries.

        This is the **write-through invalidation** strategy: after any
        mutation (POST, PUT, DELETE), the service calls
        ``cache.invalidate("funds")``, ensuring subsequent reads fetch
        fresh data from the database.
        """
        if not self._enabled:
            return 0

        keys_to_remove = [
            k for k in self._store
            if any(k.startswith(p) for p in prefixes)
        ]
        for k in keys_to_remove:
            del self._store[k]

        if keys_to_remove:
            logger.debug(
                "Cache INVALIDATED %d entries matching prefixes %s",
                len(keys_to_remove),
                prefixes,
            )
        return len(keys_to_remove)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        count = len(self._store)
        self._store.clear()
        if count:
            logger.debug("Cache CLEARED (%d entries)", count)

    def get_stats(self) -> dict:
        """Return cache statistics for monitoring / health-check endpoints."""
        total = self._hits + self._misses
        return {
            "enabled": self._enabled,
            "size": len(self._store),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "N/A",
        }


# ── Global cache instance ──
cache = TTLCache(
    ttl=settings.CACHE_TTL,
    max_size=settings.CACHE_MAX_SIZE,
    enabled=settings.CACHE_ENABLED,
)
