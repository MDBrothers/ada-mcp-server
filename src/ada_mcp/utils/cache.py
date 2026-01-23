"""Simple TTL-based cache for ALS responses."""

import asyncio
import functools
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class CacheEntry(Generic[T]):
    """Cache entry with value and expiration time."""

    value: T
    expires_at: float
    created_at: float = field(default_factory=time.monotonic)

    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at

    @property
    def age_seconds(self) -> float:
        """Return age of cache entry in seconds."""
        return time.monotonic() - self.created_at


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        """Return cache hit rate as a percentage."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    def reset(self) -> None:
        """Reset all statistics."""
        self.hits = 0
        self.misses = 0
        self.evictions = 0


@dataclass
class TTLCache(Generic[T]):
    """
    Simple TTL-based cache for ALS responses.

    Thread-safe via asyncio locks.
    """

    ttl_seconds: float = 5.0
    max_entries: int = 1000
    _cache: dict[str, CacheEntry[T]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _stats: CacheStats = field(default_factory=CacheStats)

    @property
    def stats(self) -> CacheStats:
        """Return cache statistics."""
        return self._stats

    @property
    def size(self) -> int:
        """Return current number of cached entries."""
        return len(self._cache)

    async def get(self, key: str) -> T | None:
        """Get cached value if not expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats.misses += 1
                return None
            if entry.is_expired():
                del self._cache[key]
                self._stats.misses += 1
                self._stats.evictions += 1
                return None
            self._stats.hits += 1
            return entry.value

    async def set(self, key: str, value: T) -> None:
        """Set cache value with TTL."""
        async with self._lock:
            # Evict expired entries if at max capacity
            if len(self._cache) >= self.max_entries:
                await self._evict_expired_unlocked()

            self._cache[key] = CacheEntry(
                value=value, expires_at=time.monotonic() + self.ttl_seconds
            )

    async def get_or_set(self, key: str, factory: Callable[[], Any]) -> T:
        """Get cached value or compute and cache it."""
        cached = await self.get(key)
        if cached is not None:
            return cached

        # Compute value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()

        await self.set(key, value)
        return value

    async def invalidate(self, key: str) -> None:
        """Remove specific key from cache."""
        async with self._lock:
            if self._cache.pop(key, None) is not None:
                self._stats.evictions += 1

    async def invalidate_prefix(self, prefix: str) -> None:
        """Remove all keys starting with prefix."""
        async with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]
                self._stats.evictions += 1

    async def invalidate_file(self, file_path: str) -> None:
        """Invalidate all cache entries related to a file."""
        # Normalize file path for consistent matching
        normalized = os.path.normpath(file_path)
        await self.invalidate_prefix(f"file:{normalized}")

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.evictions += count

    async def _evict_expired_unlocked(self) -> None:
        """Evict expired entries (must hold lock)."""
        now = time.monotonic()
        keys_to_remove = [k for k, v in self._cache.items() if v.expires_at < now]
        for key in keys_to_remove:
            del self._cache[key]
            self._stats.evictions += 1


def make_cache_key(*args: Any, **kwargs: Any) -> str:
    """Create a cache key from function arguments."""
    key_data = {
        "args": [str(a) for a in args],
        "kwargs": {k: str(v) for k, v in sorted(kwargs.items())},
    }
    key_str = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_str.encode()).hexdigest()


def cached(
    cache: TTLCache[Any],
    key_prefix: str = "",
) -> Callable[[Callable[P, Any]], Callable[P, Any]]:
    """
    Decorator to cache async function results.

    Usage:
        @cached(hover_cache, key_prefix="hover")
        async def get_hover_info(file: str, line: int, col: int) -> dict:
            ...
    """

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            # Build cache key
            cache_key = f"{key_prefix}:{make_cache_key(*args, **kwargs)}"

            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {key_prefix}")
                return cached_value

            # Call function and cache result
            logger.debug(f"Cache miss for {key_prefix}")
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result)
            return result

        return wrapper

    return decorator


def cached_with_file_invalidation(
    cache: TTLCache[Any],
    key_prefix: str = "",
    file_arg_name: str = "file",
) -> Callable[[Callable[P, Any]], Callable[P, Any]]:
    """
    Decorator to cache async function results with file-based cache key.

    The cache key includes the file path, making it easy to invalidate
    all cache entries for a specific file when it changes.

    Usage:
        @cached_with_file_invalidation(hover_cache, key_prefix="hover")
        async def get_hover_info(file: str, line: int, col: int) -> dict:
            ...
    """

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            # Extract file path from arguments
            # Try kwargs first, then positional args
            file_path = kwargs.get(file_arg_name)
            if file_path is None and args:
                # Assume first arg is file path
                file_path = args[0]

            # Build cache key with file prefix
            if file_path:
                normalized_path = os.path.normpath(str(file_path))
                cache_key = f"file:{normalized_path}:{key_prefix}:{make_cache_key(*args, **kwargs)}"
            else:
                cache_key = f"{key_prefix}:{make_cache_key(*args, **kwargs)}"

            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {key_prefix} ({file_path})")
                return cached_value

            # Call function and cache result
            logger.debug(f"Cache miss for {key_prefix} ({file_path})")
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result)
            return result

        return wrapper

    return decorator


# Get TTL from environment variable with defaults
_cache_ttl = float(os.environ.get("ADA_MCP_CACHE_TTL", "5"))

# Global caches for different data types
symbol_cache: TTLCache[Any] = TTLCache(ttl_seconds=10.0)
hover_cache: TTLCache[Any] = TTLCache(ttl_seconds=30.0)
definition_cache: TTLCache[Any] = TTLCache(ttl_seconds=_cache_ttl)
references_cache: TTLCache[Any] = TTLCache(ttl_seconds=_cache_ttl)
completions_cache: TTLCache[Any] = TTLCache(ttl_seconds=2.0)  # Short TTL for dynamic content


async def invalidate_file_caches(file_path: str) -> None:
    """Invalidate all caches for a specific file."""
    await symbol_cache.invalidate_file(file_path)
    await hover_cache.invalidate_file(file_path)
    await definition_cache.invalidate_file(file_path)
    await references_cache.invalidate_file(file_path)
    await completions_cache.invalidate_file(file_path)
    logger.debug(f"Invalidated all caches for {file_path}")


async def clear_all_caches() -> None:
    """Clear all caches."""
    await symbol_cache.clear()
    await hover_cache.clear()
    await definition_cache.clear()
    await references_cache.clear()
    await completions_cache.clear()
    logger.debug("Cleared all caches")


def get_cache_stats() -> dict[str, dict[str, Any]]:
    """Get statistics for all caches."""
    return {
        "symbol_cache": {
            "size": symbol_cache.size,
            "hits": symbol_cache.stats.hits,
            "misses": symbol_cache.stats.misses,
            "hit_rate": f"{symbol_cache.stats.hit_rate:.1f}%",
        },
        "hover_cache": {
            "size": hover_cache.size,
            "hits": hover_cache.stats.hits,
            "misses": hover_cache.stats.misses,
            "hit_rate": f"{hover_cache.stats.hit_rate:.1f}%",
        },
        "definition_cache": {
            "size": definition_cache.size,
            "hits": definition_cache.stats.hits,
            "misses": definition_cache.stats.misses,
            "hit_rate": f"{definition_cache.stats.hit_rate:.1f}%",
        },
        "references_cache": {
            "size": references_cache.size,
            "hits": references_cache.stats.hits,
            "misses": references_cache.stats.misses,
            "hit_rate": f"{references_cache.stats.hit_rate:.1f}%",
        },
        "completions_cache": {
            "size": completions_cache.size,
            "hits": completions_cache.stats.hits,
            "misses": completions_cache.stats.misses,
            "hit_rate": f"{completions_cache.stats.hit_rate:.1f}%",
        },
    }
