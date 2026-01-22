"""Simple TTL-based cache for ALS responses."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Cache entry with value and expiration time."""

    value: T
    expires_at: float

    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


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

    async def get(self, key: str) -> T | None:
        """Get cached value if not expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._cache[key]
                return None
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

    async def invalidate(self, key: str) -> None:
        """Remove specific key from cache."""
        async with self._lock:
            self._cache.pop(key, None)

    async def invalidate_prefix(self, prefix: str) -> None:
        """Remove all keys starting with prefix."""
        async with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()

    async def _evict_expired_unlocked(self) -> None:
        """Evict expired entries (must hold lock)."""
        now = time.monotonic()
        keys_to_remove = [k for k, v in self._cache.items() if v.expires_at < now]
        for key in keys_to_remove:
            del self._cache[key]


# Global caches for different data types
symbol_cache: TTLCache[Any] = TTLCache(ttl_seconds=10.0)
hover_cache: TTLCache[Any] = TTLCache(ttl_seconds=30.0)
