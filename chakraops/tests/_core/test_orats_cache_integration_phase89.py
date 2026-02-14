# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.9: ORATS cache integration — strikes, iv_rank use cache layer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.data.cache_store import (
    fetch_batch_with_cache,
    fetch_with_cache,
    reset_cache_stats,
)


def test_fetch_with_cache_key_includes_params(tmp_path: Path):
    """Cache key includes normalized params (sorted)."""
    reset_cache_stats()
    with (
        patch("app.core.data.cache_store.CACHE_DIR", tmp_path),
        patch("app.core.data.cache_store.CACHE_ENABLED", True),
    ):
        params = {"as_of": "2026-02-13", "dte_min": 30, "dte_max": 45}
        fetcher = MagicMock(return_value=[{"strike": 100}])
        fetch_with_cache("strikes", "AAPL", params, 60, fetcher)
        fetcher.assert_called_once()
        # Second call should hit cache (params normalization yields same key)
        result = fetch_with_cache("strikes", "AAPL", params, 60, fetcher)
        assert result == [{"strike": 100}]
        assert fetcher.call_count == 1


def test_fetch_batch_with_cache_strikes_iv_rank(tmp_path: Path):
    """fetch_batch_with_cache wraps batch fetcher; key uses sorted symbols."""
    reset_cache_stats()
    with (
        patch("app.core.data.cache_store.CACHE_DIR", tmp_path),
        patch("app.core.data.cache_store.CACHE_ENABLED", True),
    ):
        params = {"as_of": "2026-02-13"}
        fetcher = MagicMock(return_value={"AAPL": {"iv_rank": 0.5}, "MSFT": {"iv_rank": 0.6}})
        result = fetch_batch_with_cache("iv_rank", ["MSFT", "AAPL"], params, 60, fetcher)
        assert result == {"AAPL": {"iv_rank": 0.5}, "MSFT": {"iv_rank": 0.6}}
        fetcher.assert_called_once()
        # Same batch (different order) should hit cache
        result2 = fetch_batch_with_cache("iv_rank", ["AAPL", "MSFT"], params, 60, fetcher)
        assert result2 == {"AAPL": {"iv_rank": 0.5}, "MSFT": {"iv_rank": 0.6}}
        assert fetcher.call_count == 1
