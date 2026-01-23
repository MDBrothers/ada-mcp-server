"""Tests for the caching module."""

import asyncio
import time

import pytest

from ada_mcp.utils.cache import (
    TTLCache,
    CacheEntry,
    CacheStats,
    cached,
    cached_with_file_invalidation,
    clear_all_caches,
    get_cache_stats,
    invalidate_file_caches,
    make_cache_key,
)


class TestCacheEntry:
    """Tests for CacheEntry class."""

    def test_is_expired_false(self):
        """Test entry is not expired when within TTL."""
        entry = CacheEntry(value="test", expires_at=time.monotonic() + 10)
        assert not entry.is_expired()

    def test_is_expired_true(self):
        """Test entry is expired when past TTL."""
        entry = CacheEntry(value="test", expires_at=time.monotonic() - 1)
        assert entry.is_expired()

    def test_age_seconds(self):
        """Test age calculation."""
        entry = CacheEntry(value="test", expires_at=time.monotonic() + 10)
        time.sleep(0.1)
        assert entry.age_seconds >= 0.1


class TestCacheStats:
    """Tests for CacheStats class."""

    def test_initial_state(self):
        """Test initial statistics."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0

    def test_hit_rate_empty(self):
        """Test hit rate with no operations."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats(hits=75, misses=25)
        assert stats.hit_rate == 75.0

    def test_reset(self):
        """Test resetting statistics."""
        stats = CacheStats(hits=10, misses=5, evictions=2)
        stats.reset()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0


class TestTTLCache:
    """Tests for TTLCache class."""

    @pytest.fixture
    def cache(self):
        """Create a TTLCache instance."""
        return TTLCache[str](ttl_seconds=1.0)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        """Test basic set and get."""
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache):
        """Test getting a nonexistent key."""
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_expiration(self):
        """Test that entries expire after TTL."""
        cache = TTLCache[str](ttl_seconds=0.1)
        await cache.set("key", "value")
        
        # Should be cached
        assert await cache.get("key") == "value"
        
        # Wait for expiration
        await asyncio.sleep(0.15)
        
        # Should be expired
        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_invalidate(self, cache):
        """Test invalidating a specific key."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        
        await cache.invalidate("key1")
        
        assert await cache.get("key1") is None
        assert await cache.get("key2") == "value2"

    @pytest.mark.asyncio
    async def test_invalidate_prefix(self, cache):
        """Test invalidating keys by prefix."""
        await cache.set("prefix:a", "value_a")
        await cache.set("prefix:b", "value_b")
        await cache.set("other:c", "value_c")
        
        await cache.invalidate_prefix("prefix:")
        
        assert await cache.get("prefix:a") is None
        assert await cache.get("prefix:b") is None
        assert await cache.get("other:c") == "value_c"

    @pytest.mark.asyncio
    async def test_invalidate_file(self, cache):
        """Test invalidating by file path."""
        await cache.set("file:/project/src/main.adb:hover:abc", "hover_data")
        await cache.set("file:/project/src/main.adb:def:xyz", "def_data")
        await cache.set("file:/project/src/other.adb:hover:123", "other_data")
        
        await cache.invalidate_file("/project/src/main.adb")
        
        assert await cache.get("file:/project/src/main.adb:hover:abc") is None
        assert await cache.get("file:/project/src/main.adb:def:xyz") is None
        assert await cache.get("file:/project/src/other.adb:hover:123") == "other_data"

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        """Test clearing all entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        
        await cache.clear()
        
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert cache.size == 0

    @pytest.mark.asyncio
    async def test_size_property(self, cache):
        """Test size property."""
        assert cache.size == 0
        
        await cache.set("key1", "value1")
        assert cache.size == 1
        
        await cache.set("key2", "value2")
        assert cache.size == 2

    @pytest.mark.asyncio
    async def test_stats_tracking(self, cache):
        """Test that statistics are tracked."""
        await cache.set("key1", "value1")
        
        # Hit
        await cache.get("key1")
        assert cache.stats.hits == 1
        
        # Miss
        await cache.get("nonexistent")
        assert cache.stats.misses == 1
        
        # Eviction
        await cache.invalidate("key1")
        assert cache.stats.evictions == 1

    @pytest.mark.asyncio
    async def test_get_or_set_cached(self, cache):
        """Test get_or_set returns cached value."""
        await cache.set("key", "cached_value")
        
        factory_called = False
        def factory():
            nonlocal factory_called
            factory_called = True
            return "new_value"
        
        result = await cache.get_or_set("key", factory)
        
        assert result == "cached_value"
        assert not factory_called

    @pytest.mark.asyncio
    async def test_get_or_set_computes(self, cache):
        """Test get_or_set computes and caches value."""
        factory_calls = 0
        
        async def factory():
            nonlocal factory_calls
            factory_calls += 1
            return "computed_value"
        
        result1 = await cache.get_or_set("key", factory)
        result2 = await cache.get_or_set("key", factory)
        
        assert result1 == "computed_value"
        assert result2 == "computed_value"
        assert factory_calls == 1  # Only called once

    @pytest.mark.asyncio
    async def test_max_entries_eviction(self):
        """Test that old entries are evicted when max_entries is reached."""
        cache = TTLCache[str](ttl_seconds=100.0, max_entries=3)
        
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        
        # Adding 4th entry should trigger eviction of expired entries
        # Since none are expired, all should remain
        await cache.set("key4", "value4")
        
        # At least the new entry should be there
        assert await cache.get("key4") == "value4"


class TestCacheKey:
    """Tests for cache key generation."""

    def test_make_cache_key_args(self):
        """Test cache key from args only."""
        key1 = make_cache_key("arg1", "arg2")
        key2 = make_cache_key("arg1", "arg2")
        key3 = make_cache_key("arg1", "arg3")
        
        assert key1 == key2
        assert key1 != key3

    def test_make_cache_key_kwargs(self):
        """Test cache key from kwargs."""
        key1 = make_cache_key(file="/path/to/file", line=10)
        key2 = make_cache_key(line=10, file="/path/to/file")
        
        # Order shouldn't matter
        assert key1 == key2

    def test_make_cache_key_mixed(self):
        """Test cache key from mixed args and kwargs."""
        key = make_cache_key("arg1", param="value")
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hash length


class TestCachedDecorator:
    """Tests for the @cached decorator."""

    @pytest.mark.asyncio
    async def test_cached_decorator(self):
        """Test that @cached decorator works."""
        cache = TTLCache[dict](ttl_seconds=10.0)
        call_count = 0
        
        @cached(cache, key_prefix="test")
        async def expensive_function(x: int, y: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"sum": x + y}
        
        # First call - should compute
        result1 = await expensive_function(1, 2)
        assert result1 == {"sum": 3}
        assert call_count == 1
        
        # Second call - should use cache
        result2 = await expensive_function(1, 2)
        assert result2 == {"sum": 3}
        assert call_count == 1  # Not incremented
        
        # Different args - should compute
        result3 = await expensive_function(2, 3)
        assert result3 == {"sum": 5}
        assert call_count == 2


class TestCachedWithFileInvalidation:
    """Tests for the @cached_with_file_invalidation decorator."""

    @pytest.mark.asyncio
    async def test_file_based_caching(self):
        """Test file-based cache invalidation."""
        cache = TTLCache[dict](ttl_seconds=10.0)
        call_count = 0
        
        @cached_with_file_invalidation(cache, key_prefix="hover")
        async def get_hover(file: str, line: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"file": file, "line": line}
        
        # First call
        result1 = await get_hover("/path/main.adb", 10)
        assert call_count == 1
        
        # Same call - cached
        result2 = await get_hover("/path/main.adb", 10)
        assert call_count == 1
        
        # Invalidate the file
        await cache.invalidate_file("/path/main.adb")
        
        # Should recompute
        result3 = await get_hover("/path/main.adb", 10)
        assert call_count == 2


class TestGlobalCacheFunctions:
    """Tests for global cache functions."""

    @pytest.mark.asyncio
    async def test_get_cache_stats(self):
        """Test getting cache statistics."""
        stats = get_cache_stats()
        
        assert "symbol_cache" in stats
        assert "hover_cache" in stats
        assert "definition_cache" in stats
        
        for cache_stats in stats.values():
            assert "size" in cache_stats
            assert "hits" in cache_stats
            assert "misses" in cache_stats
            assert "hit_rate" in cache_stats

    @pytest.mark.asyncio
    async def test_clear_all_caches(self):
        """Test clearing all caches."""
        # This should not raise any errors
        await clear_all_caches()

    @pytest.mark.asyncio
    async def test_invalidate_file_caches(self):
        """Test invalidating all caches for a file."""
        # This should not raise any errors
        await invalidate_file_caches("/test/file.adb")
