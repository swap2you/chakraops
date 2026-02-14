# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.8: Lightweight file-based cache for ORATS data.

TTL policy (Phase 6 staleness concepts):
- price, bid/ask/volume/oi: TTL 60 seconds
- iv_rank: TTL 1 day (86400) or 6 hours (21600)
- calendar/events: TTL 1 day (86400)

Keys include endpoint + symbol + as_of date. Atomic writes (temp + rename).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config.eval_config import CACHE_DIR, CACHE_ENABLED

logger = logging.getLogger(__name__)

# TTL defaults (seconds)
TTL_PRICE = 60
TTL_BID_ASK_VOLUME_OI = 60
TTL_IV_RANK = 86400  # 1 day
TTL_CALENDAR_EVENTS = 86400  # 1 day

# Stats
_cache_hits = 0
_cache_misses = 0


def _safe_key(key: str) -> str:
    """Sanitize key for filename (alphanumeric, underscore)."""
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in key[:64]) + "_" + h


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_safe_key(key)}.json"


def cache_get(key: str) -> Optional[Dict[str, Any]]:
    """Load cached value by key. Returns None if missing or invalid."""
    global _cache_hits
    if not CACHE_ENABLED:
        return None
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("[CACHE] get %s failed: %s", key[:50], e)
        return None


def cache_set(key: str, value: Dict[str, Any]) -> None:
    """Store value with atomic write (temp + rename)."""
    if not CACHE_ENABLED:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(key)
    data = dict(value)
    if "cached_at" not in data:
        data["cached_at"] = datetime.now(timezone.utc).isoformat()
    fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, prefix="cache_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def is_fresh(cached_item: Dict[str, Any], ttl_seconds: int) -> bool:
    """True if cached_at within ttl_seconds of now."""
    if not cached_item or ttl_seconds <= 0:
        return False
    at = cached_item.get("cached_at")
    if not at:
        return False
    try:
        dt = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - dt).total_seconds()
        return elapsed < ttl_seconds
    except (ValueError, TypeError):
        return False


def cache_hits() -> int:
    return _cache_hits


def cache_misses() -> int:
    return _cache_misses


def cache_stats() -> Dict[str, Any]:
    """Return cache hit/miss stats for logging."""
    total = _cache_hits + _cache_misses
    hit_rate = 100.0 * _cache_hits / total if total > 0 else 0.0
    return {
        "cache_hits": _cache_hits,
        "cache_misses": _cache_misses,
        "cache_hit_rate_pct": round(hit_rate, 1),
        "cache_enabled": CACHE_ENABLED,
    }


def _record_hit() -> None:
    global _cache_hits
    _cache_hits += 1


def _record_miss() -> None:
    global _cache_misses
    _cache_misses += 1


def reset_cache_stats() -> None:
    """Reset hit/miss counters (for tests)."""
    global _cache_hits, _cache_misses
    _cache_hits = 0
    _cache_misses = 0


def fetch_with_cache(
    endpoint_name: str,
    symbol: str,
    params: Dict[str, Any],
    ttl_seconds: int,
    fetcher: Any,
) -> Any:
    """
    Phase 8.8: Cache-aware fetch wrapper.
    If cache enabled and fresh -> return cached.
    Else call fetcher(), store response, return.
    If fetcher raises -> do NOT cache; re-raise.
    """
    from datetime import date

    if not CACHE_ENABLED:
        return fetcher()

    as_of = params.get("as_of") or date.today().isoformat()
    key = f"{endpoint_name}:{symbol.upper()}:{as_of}"

    cached = cache_get(key)
    if cached is not None and is_fresh(cached, ttl_seconds):
        _record_hit()
        return cached.get("value")

    _record_miss()
    try:
        result = fetcher()
        cache_set(key, {"value": result, "cached_at": datetime.now(timezone.utc).isoformat()})
        return result
    except Exception:
        # Do NOT cache errors
        raise
