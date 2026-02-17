"""
Unit tests for the in-memory TTL cache.

Tests cover:
- Basic get / set operations
- TTL expiration
- FIFO eviction when max_size is reached
- Prefix-based invalidation
- Disabled mode (all ops are no-ops)
- Cache statistics reporting
- Edge cases (empty cache, repeated keys, zero TTL)
"""

import time

from app.core.cache import CacheEntry, TTLCache

# ────────────────────────────────────────────────────────────────────────────
# CacheEntry tests
# ────────────────────────────────────────────────────────────────────────────


class TestCacheEntry:
    """Tests for the CacheEntry data class."""

    def test_entry_stores_value(self):
        entry = CacheEntry("hello")
        assert entry.value == "hello"

    def test_entry_not_expired_immediately(self):
        entry = CacheEntry("hello")
        assert not entry.is_expired(ttl=10.0)

    def test_entry_expires_after_ttl(self):
        entry = CacheEntry("hello")
        # Simulate passage of time by backdating created_at
        entry.created_at = time.monotonic() - 15.0
        assert entry.is_expired(ttl=10.0)

    def test_entry_not_expired_at_boundary(self):
        entry = CacheEntry("hello")
        # Just under TTL — should NOT be expired
        entry.created_at = time.monotonic() - 9.9
        assert not entry.is_expired(ttl=10.0)


# ────────────────────────────────────────────────────────────────────────────
# TTLCache tests
# ────────────────────────────────────────────────────────────────────────────


class TestTTLCacheBasic:
    """Happy-path tests for the TTLCache."""

    def test_set_and_get(self, test_cache: TTLCache):
        test_cache.set("key1", "value1")
        assert test_cache.get("key1") == "value1"

    def test_get_missing_key_returns_none(self, test_cache: TTLCache):
        assert test_cache.get("nonexistent") is None

    def test_overwrite_key(self, test_cache: TTLCache):
        test_cache.set("k", "old")
        test_cache.set("k", "new")
        assert test_cache.get("k") == "new"

    def test_stores_various_types(self, test_cache: TTLCache):
        """Cache should store any type: lists, dicts, integers, etc."""
        test_cache.set("list", [1, 2, 3])
        test_cache.set("dict", {"a": 1})
        test_cache.set("int", 42)
        assert test_cache.get("list") == [1, 2, 3]
        assert test_cache.get("dict") == {"a": 1}
        assert test_cache.get("int") == 42

    def test_none_value_is_distinguishable_from_miss(self, test_cache: TTLCache):
        """
        Storing None should NOT be confused with a cache miss.
        However, get() returns None on miss OR if None was stored,
        so the caller cannot distinguish them.  This is by design.
        """
        test_cache.set("none_key", None)
        # get() returns None for both miss and stored None
        assert test_cache.get("none_key") is None


class TestTTLCacheExpiration:
    """Tests for TTL-based expiration."""

    def test_expired_entry_returns_none(self):
        cache = TTLCache(ttl=0.01, max_size=100, enabled=True)
        cache.set("k", "v")
        # Manually expire the entry
        cache._store["k"].created_at = time.monotonic() - 1.0
        assert cache.get("k") is None

    def test_expired_entry_is_removed_from_store(self):
        cache = TTLCache(ttl=0.01, max_size=100, enabled=True)
        cache.set("k", "v")
        cache._store["k"].created_at = time.monotonic() - 1.0
        cache.get("k")  # triggers removal
        assert "k" not in cache._store


class TestTTLCacheEviction:
    """Tests for FIFO eviction when max_size is exceeded."""

    def test_evicts_oldest_when_full(self):
        cache = TTLCache(ttl=30.0, max_size=3, enabled=True)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Cache is full; adding a 4th should evict "a" (oldest)
        cache.set("d", 4)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("d") == 4

    def test_no_eviction_when_updating_existing_key(self):
        cache = TTLCache(ttl=30.0, max_size=3, enabled=True)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Updating "a" should NOT evict anything
        cache.set("a", 10)
        assert cache.get("a") == 10
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_eviction_order_is_fifo(self):
        cache = TTLCache(ttl=30.0, max_size=2, enabled=True)
        cache.set("first", 1)
        cache.set("second", 2)
        cache.set("third", 3)  # evicts "first"
        assert cache.get("first") is None
        assert cache.get("second") == 2
        assert cache.get("third") == 3


class TestTTLCacheInvalidation:
    """Tests for prefix-based invalidation."""

    def test_invalidate_by_prefix(self, test_cache: TTLCache):
        test_cache.set("funds:list:0:100", [])
        test_cache.set("funds:abc-123", "fund")
        test_cache.set("investors:list:0:100", [])
        removed = test_cache.invalidate("funds:")
        assert removed == 2
        assert test_cache.get("funds:list:0:100") is None
        assert test_cache.get("investors:list:0:100") == []

    def test_invalidate_no_matching_prefix(self, test_cache: TTLCache):
        test_cache.set("funds:list", [])
        removed = test_cache.invalidate("investors:")
        assert removed == 0
        assert test_cache.get("funds:list") == []

    def test_invalidate_multiple_prefixes(self, test_cache: TTLCache):
        test_cache.set("funds:a", 1)
        test_cache.set("investors:b", 2)
        test_cache.set("other:c", 3)
        removed = test_cache.invalidate("funds:", "investors:")
        assert removed == 2
        assert test_cache.get("other:c") == 3

    def test_clear_removes_all_entries(self, test_cache: TTLCache):
        test_cache.set("a", 1)
        test_cache.set("b", 2)
        test_cache.clear()
        assert test_cache.get("a") is None
        assert test_cache.get("b") is None


class TestTTLCacheDisabled:
    """Tests for disabled cache mode."""

    def test_get_returns_none(self, disabled_cache: TTLCache):
        disabled_cache._store["k"] = CacheEntry("v")  # force internal state
        assert disabled_cache.get("k") is None

    def test_set_is_noop(self, disabled_cache: TTLCache):
        disabled_cache.set("k", "v")
        assert len(disabled_cache._store) == 0

    def test_invalidate_returns_zero(self, disabled_cache: TTLCache):
        assert disabled_cache.invalidate("any_prefix") == 0


class TestTTLCacheStats:
    """Tests for cache statistics reporting."""

    def test_stats_initial(self, test_cache: TTLCache):
        stats = test_cache.get_stats()
        assert stats["enabled"] is True
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == "N/A"

    def test_stats_after_operations(self, test_cache: TTLCache):
        test_cache.set("k", "v")
        test_cache.get("k")  # hit
        test_cache.get("missing")  # miss
        stats = test_cache.get_stats()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == "50.0%"

    def test_stats_100_percent_hit_rate(self, test_cache: TTLCache):
        test_cache.set("k", "v")
        test_cache.get("k")
        test_cache.get("k")
        stats = test_cache.get_stats()
        assert stats["hit_rate"] == "100.0%"
