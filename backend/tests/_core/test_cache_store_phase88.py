# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.8: Cache Store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.data.cache_store import cache_get, cache_set, is_fresh


def test_cache_set_get_roundtrip(tmp_path: Path):
    """cache_set and cache_get roundtrip."""
    with (
        patch("app.core.data.cache_store.CACHE_DIR", tmp_path),
        patch("app.core.data.cache_store.CACHE_ENABLED", True),
    ):
        cache_set("test:key:1", {"value": {"foo": 42}, "cached_at": datetime.now(timezone.utc).isoformat()})
        out = cache_get("test:key:1")
        assert out is not None
        assert out.get("value") == {"foo": 42}


def test_cache_ttl_freshness():
    """is_fresh True when cached_at within ttl, False otherwise."""
    now = datetime.now(timezone.utc)
    item = {"cached_at": now.isoformat(), "value": 1}
    assert is_fresh(item, 60) is True
    old = now - timedelta(seconds=120)
    item_old = {"cached_at": old.isoformat(), "value": 1}
    assert is_fresh(item_old, 60) is False


def test_cache_atomic_write(tmp_path: Path):
    """cache_set creates file (atomic write)."""
    with (
        patch("app.core.data.cache_store.CACHE_DIR", tmp_path),
        patch("app.core.data.cache_store.CACHE_ENABLED", True),
    ):
        cache_set("atomic:key", {"value": "test"})
        files = list(tmp_path.glob("*.json"))
        assert len(files) >= 1
