import time

from vidasync_multiagents_ia.core.cache import TTLCache


def test_ttl_cache_disabled_when_ttl_zero() -> None:
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=0.0, max_entries=4)
    assert cache.enabled is False
    cache.set("a", 1)
    assert cache.get("a") is None


def test_ttl_cache_hit_before_expiration() -> None:
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=60.0, max_entries=4)
    cache.set("a", 1)
    assert cache.get("a") == 1


def test_ttl_cache_miss_after_expiration() -> None:
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=0.01, max_entries=4)
    cache.set("a", 1)
    time.sleep(0.02)
    assert cache.get("a") is None


def test_ttl_cache_lru_evicts_oldest() -> None:
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=60.0, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")
    cache.set("c", 3)
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_ttl_cache_clear() -> None:
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=60.0, max_entries=4)
    cache.set("a", 1)
    cache.clear()
    assert cache.get("a") is None
    assert len(cache) == 0
