# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for ORATS daily candle provider. Mock requests.get."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.core.eligibility.providers.orats_daily_provider import (
    OratsDailyProvider,
    _normalize_row,
)


def test_normalize_row():
    """Correct normalization from ORATS field names."""
    row = {
        "tradeDate": "2024-01-15",
        "openPx": 100.5,
        "hiPx": 101.0,
        "loPx": 99.0,
        "clsPx": 100.0,
        "stockVolume": 1_000_000,
    }
    out = _normalize_row(row)
    assert out["ts"] == "2024-01-15"
    assert out["open"] == 100.5
    assert out["high"] == 101.0
    assert out["low"] == 99.0
    assert out["close"] == 100.0
    assert out["volume"] == 1_000_000


def test_normalize_row_empty_returns_none_fields():
    """Missing fields yield None where appropriate."""
    out = _normalize_row({})
    assert out["ts"] is None
    assert out["open"] is None
    assert out["close"] is None


@patch("app.core.eligibility.providers.orats_daily_provider.requests.get")
def test_get_daily_normalization_and_lookback(mock_get, tmp_path):
    """Full dataset returned; sort ascending; slice last lookback. Use tmp_path so cache is empty."""
    raw_data = [
        {"tradeDate": "2024-01-01", "openPx": 100, "hiPx": 101, "loPx": 99, "clsPx": 100.5, "stockVolume": 500},
        {"tradeDate": "2024-01-02", "openPx": 100.5, "hiPx": 102, "loPx": 100, "clsPx": 101, "stockVolume": 600},
        {"tradeDate": "2024-01-03", "openPx": 101, "hiPx": 103, "loPx": 100.5, "clsPx": 102, "stockVolume": 700},
        {"tradeDate": "2024-01-04", "openPx": 102, "hiPx": 104, "loPx": 101, "clsPx": 103, "stockVolume": 800},
        {"tradeDate": "2024-01-05", "openPx": 103, "hiPx": 105, "loPx": 102, "clsPx": 104, "stockVolume": 900},
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": raw_data}
    mock_resp.text = ""
    mock_get.return_value = mock_resp

    provider = OratsDailyProvider(token="test-token", cache_dir=tmp_path)
    out = provider.get_daily("SPY", lookback=3)
    assert len(out) == 3
    assert out[0]["ts"] == "2024-01-03"
    assert out[-1]["ts"] == "2024-01-05"
    assert out[0]["close"] == 102.0
    assert out[-1]["close"] == 104.0


@patch("app.core.eligibility.providers.orats_daily_provider.requests.get")
def test_get_daily_empty_data_returns_empty_list(mock_get, tmp_path):
    """Empty data => return []."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": []}
    mock_get.return_value = mock_resp

    provider = OratsDailyProvider(token="test-token", cache_dir=tmp_path)
    out = provider.get_daily("SPY", lookback=400)
    assert out == []


@patch("app.core.eligibility.providers.orats_daily_provider.requests.get")
def test_get_daily_non_200_returns_empty_list(mock_get, tmp_path):
    """status != 200 => log and return []."""
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"
    mock_get.return_value = mock_resp

    provider = OratsDailyProvider(token="test-token", cache_dir=tmp_path)
    out = provider.get_daily("SPY", lookback=400)
    assert out == []


def test_missing_token_raises():
    """Provider with empty token raises ValueError."""
    with pytest.raises(ValueError, match="token"):
        OratsDailyProvider(token="")
    with pytest.raises(ValueError, match="token"):
        OratsDailyProvider(token="   ")


@patch("app.core.eligibility.providers.orats_daily_provider.requests.get")
def test_cache_load_works(mock_get, tmp_path):
    """When cache exists and is from today, load from cache (no request)."""
    cached = [
        {"ts": "2024-01-10", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1_000_000},
        {"ts": "2024-01-11", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1_100_000},
    ]
    cache_file = tmp_path / "SPY.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cached, f)
    mock_get.side_effect = AssertionError("Request must not be called when cache hit")

    provider = OratsDailyProvider(token="test-token", cache_dir=tmp_path)
    out = provider.get_daily("SPY", lookback=10)
    assert len(out) == 2
    assert out[0]["ts"] == "2024-01-10"
    assert out[1]["close"] == 101.0


@patch("app.core.eligibility.providers.orats_daily_provider.requests.get")
def test_provider_returns_minimum_lookback_rows(mock_get, tmp_path):
    """When API returns 500 rows and lookback=300, returned list has 300 rows (last N)."""
    raw_data = [
        {
            "tradeDate": f"2024-01-{(i % 28) + 1:02d}",
            "openPx": 100 + i * 0.1,
            "hiPx": 101,
            "loPx": 99,
            "clsPx": 100,
            "stockVolume": 500,
        }
        for i in range(500)
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": raw_data}
    mock_get.return_value = mock_resp
    provider = OratsDailyProvider(token="test-token", cache_dir=tmp_path)
    out = provider.get_daily("SPY", lookback=300)
    assert len(out) == 300
    assert out[0]["ts"] is not None
    assert out[-1]["close"] is not None


@patch("app.core.eligibility.providers.orats_daily_provider.requests.get")
def test_cache_today_prevents_http_call(mock_get, tmp_path):
    """When cache file exists and is from today, get_daily does not call requests.get."""
    (tmp_path / "CACHE.json").write_text(
        json.dumps([{"ts": "2024-06-01", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1_000_000}]),
        encoding="utf-8",
    )
    (tmp_path / "CACHE.json").touch()
    mock_get.side_effect = AssertionError("HTTP must not be called when cache hit")
    provider = OratsDailyProvider(token="test-token", cache_dir=tmp_path)
    out = provider.get_daily("CACHE", lookback=100)
    assert len(out) == 1
    assert out[0]["close"] == 100


@patch("app.core.eligibility.providers.orats_daily_provider.requests.get")
def test_fetch_saves_cache(mock_get, tmp_path):
    """After fetch, cache is written."""
    raw_data = [
        {"tradeDate": "2024-01-01", "openPx": 100, "hiPx": 101, "loPx": 99, "clsPx": 100, "stockVolume": 500},
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": raw_data}
    mock_get.return_value = mock_resp

    provider = OratsDailyProvider(token="test-token", cache_dir=tmp_path)
    out = provider.get_daily("NVDA", lookback=400)
    assert len(out) == 1
    assert (tmp_path / "NVDA.json").exists()
    with open(tmp_path / "NVDA.json", encoding="utf-8") as f:
        saved = json.load(f)
    assert len(saved) == 1
    assert saved[0].get("ts") == "2024-01-01"
    assert saved[0].get("close") == 100.0
