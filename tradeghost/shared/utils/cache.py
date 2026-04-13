from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheItem(Generic[V]):
    value: V
    expires_at: float


class TTLCache(Generic[K, V]):
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[K, CacheItem[V]] = {}

    def get(self, key: K) -> V | None:
        item = self._store.get(key)
        if item is None:
            return None
        if time.time() >= item.expires_at:
            self._store.pop(key, None)
            return None
        return item.value

    def set(self, key: K, value: V) -> None:
        self._store[key] = CacheItem(value=value, expires_at=time.time() + self.ttl_seconds)

