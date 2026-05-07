"""Redis cache layer — in-memory fallback if Redis unavailable."""
from __future__ import annotations

import json
import time
from typing import Any

from .logging_service import get_logger

log = get_logger(__name__)

# ── Try to connect Redis, fall back to in-memory dict ────────────────────────
_redis = None
_memory_cache: dict[str, tuple[Any, float]] = {}   # key → (value, expires_at)


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis as redis_lib
        from .settings import get_settings
        s = get_settings()
        url = getattr(s, "redis_url", None)
        if url:
            _redis = redis_lib.from_url(url, decode_responses=True, socket_timeout=2)
            _redis.ping()
            log.info("Redis connected: %s", url[:40])
        else:
            log.info("REDIS_URL not set — using in-memory cache")
    except Exception as e:
        log.warning("Redis unavailable (%s) — falling back to in-memory cache", e)
        _redis = None
    return _redis


def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """Store value with TTL (seconds). Falls back to in-memory."""
    r = _get_redis()
    serialized = json.dumps(value)
    if r:
        try:
            r.setex(key, ttl, serialized)
            return
        except Exception as e:
            log.warning("Redis set failed: %s", e)
    # In-memory fallback
    _memory_cache[key] = (value, time.time() + ttl)


def cache_get(key: str) -> Any | None:
    """Retrieve value. Returns None if missing or expired."""
    r = _get_redis()
    if r:
        try:
            raw = r.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            log.warning("Redis get failed: %s", e)
    # In-memory fallback
    entry = _memory_cache.get(key)
    if entry:
        value, expires_at = entry
        if time.time() < expires_at:
            return value
        del _memory_cache[key]
    return None


def cache_delete(key: str) -> None:
    """Invalidate a cache key."""
    r = _get_redis()
    if r:
        try:
            r.delete(key)
        except Exception:
            pass
    _memory_cache.pop(key, None)


def cache_delete_pattern(pattern: str) -> None:
    """Invalidate all keys matching pattern (e.g. 'loads:*')."""
    r = _get_redis()
    if r:
        try:
            keys = r.keys(pattern)
            if keys:
                r.delete(*keys)
        except Exception:
            pass
    # In-memory: scan for matching prefix
    prefix = pattern.replace("*", "")
    to_delete = [k for k in _memory_cache if k.startswith(prefix)]
    for k in to_delete:
        del _memory_cache[k]


# ── Common TTLs ───────────────────────────────────────────────────────────────
TTL_LOADS      = 60      # load board — refresh every 1 min
TTL_DRIVER     = 300     # driver profile — 5 min
TTL_PAYOUT     = 120     # payout history — 2 min
TTL_DASHBOARD  = 60      # dashboard stats — 1 min
TTL_COMPLIANCE = 600     # compliance data — 10 min
TTL_CARRIERS   = 300     # carrier data — 5 min
