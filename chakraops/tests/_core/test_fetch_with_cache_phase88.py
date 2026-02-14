# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.8: fetch_with_cache wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.data.cache_store import fetch_with_cache, reset_cache_stats, cache_get, cache_set


def test_fetch_returns_cached_when_fresh(tmp_path: Path):
    """fetch_with_cache returns cached value when fresh; fetcher not invoked."""
    reset_cache_stats()
    with (
        patch("app.core.data.cache_store.CACHE_DIR", tmp_path),
        patch("app.core.data.cache_store.CACHE_ENABLED", True),
    ):
        from datetime import datetime, timezone
        # Phase 8.9: key includes normalized params (as_of=...)
        cache_set(
            "cores:AAPL:as_of=2026-02-13:2026-02-13",
            {"value": {"cached": True}, "cached_at": datetime.now(timezone.utc).isoformat()},
        )
        fetcher = MagicMock(side_effect=AssertionError("fetcher should not be called"))
        result = fetch_with_cache("cores", "AAPL", {"as_of": "2026-02-13"}, 60, fetcher)
        assert result == {"cached": True}
        fetcher.assert_not_called()


def test_fetch_calls_orats_when_stale(tmp_path: Path):
    """fetch_with_cache calls fetcher when cache miss or stale."""
    reset_cache_stats()
    with (
        patch("app.core.data.cache_store.CACHE_DIR", tmp_path),
        patch("app.core.data.cache_store.CACHE_ENABLED", True),
    ):
        fetcher = MagicMock(return_value={"live": True})
        result = fetch_with_cache("cores", "XYZ", {"as_of": "2026-02-13"}, 60, fetcher)
        assert result == {"live": True}
        fetcher.assert_called_once()


def test_orats_error_not_cached(tmp_path: Path):
    """When fetcher raises, error is not cached and is re-raised."""
    reset_cache_stats()
    with (
        patch("app.core.data.cache_store.CACHE_DIR", tmp_path),
        patch("app.core.data.cache_store.CACHE_ENABLED", True),
    ):
        fetcher = MagicMock(side_effect=ValueError("ORATS error"))
        with pytest.raises(ValueError, match="ORATS error"):
            fetch_with_cache("cores", "ERR", {"as_of": "2026-02-13"}, 60, fetcher)
        out = cache_get("cores:ERR:as_of=2026-02-13:2026-02-13")
        assert out is None or out.get("value") != {"error": "ORATS error"}
