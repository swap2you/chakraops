# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8G: Tests for ORATS Core Data v2 — snapshot parsing, field mapping, EquitySnapshot."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.data.orats_field_map import (
    ORATS_TO_CANONICAL,
    orats_to_canonical,
    REQUIRED_CANONICAL_FIELDS,
    OPTIONAL_CANONICAL_FIELDS,
)
from app.core.data.equity_snapshot import (
    EquitySnapshot,
    build_equity_snapshot_from_core,
    REASON_NOT_PROVIDED,
)


# --- Unit: field mapping ---


def test_orats_to_canonical_maps_known_fields():
    raw = {
        "stkVolu": 10_000_000,
        "avgOptVolu20d": 50_000.5,
        "ivPctile1y": 45.2,
        "ivRank": 38.0,
        "pxCls": 175.50,
        "tradeDate": "2026-02-09",
        "confidence": 0.92,
    }
    out = orats_to_canonical(raw)
    assert out.get("stock_volume_today") == 10_000_000
    assert out.get("avg_option_volume_20d") == 50_000.5
    assert out.get("iv_percentile_1y") == 45.2
    assert out.get("iv_rank") == 38.0
    assert out.get("last_close_price") == 175.50
    assert out.get("trade_date") == "2026-02-09"
    assert out.get("orats_confidence") == 0.92


def test_orats_to_canonical_skips_unknown_keys():
    raw = {"stkVolu": 1, "unknownField": 999}
    out = orats_to_canonical(raw)
    assert "stock_volume_today" in out
    assert "unknownField" not in out


def test_orats_to_canonical_skips_none():
    raw = {"stkVolu": None, "pxCls": 100.0}
    out = orats_to_canonical(raw)
    assert "stock_volume_today" not in out
    assert out.get("last_close_price") == 100.0


# --- Unit: EquitySnapshot ---


def test_equity_snapshot_to_dict_no_unknown():
    s = EquitySnapshot(
        ticker="AAPL",
        trade_date="2026-02-09",
        last_close_price=175.5,
        stock_volume_today=10_000_000,
        source="ORATS_CORE",
        missing_fields=[],
        missing_reasons={},
    )
    d = s.to_dict()
    assert d["ticker"] == "AAPL"
    assert d["last_close_price"] == 175.5
    assert "UNKNOWN" not in str(d).upper() or "unknown" not in str(d)


# --- Integration: mock /datav2/cores (AAPL) ---


@patch("app.core.orats.orats_core_client.fetch_core_snapshot")
def test_build_equity_snapshot_from_core_no_unknown_when_orats_provides_data(mock_fetch):
    mock_fetch.return_value = {
        "ticker": "AAPL",
        "stkVolu": 12_000_000,
        "avgOptVolu20d": 55_000.0,
        "ivPctile1y": 42.0,
        "ivRank": 35.0,
        "pxCls": 178.25,
        "priorCls": 177.00,
        "tradeDate": "2026-02-09",
        "confidence": 0.95,
        "sector": "Technology",
        "marketCap": 2_800_000_000_000,
        "industry": "Consumer Electronics",
    }
    snapshot = build_equity_snapshot_from_core("AAPL", token="test-token")
    assert snapshot.ticker == "AAPL"
    assert snapshot.last_close_price == 178.25
    assert snapshot.stock_volume_today == 12_000_000
    assert snapshot.avg_option_volume_20d == 55_000.0
    assert snapshot.iv_rank == 35.0
    assert snapshot.trade_date == "2026-02-09"
    assert snapshot.sector == "Technology"
    for name in REQUIRED_CANONICAL_FIELDS:
        if name == "ticker":
            continue
        assert name not in snapshot.missing_fields, f"Required field {name} should be populated"
    assert "UNKNOWN" not in str(snapshot.missing_reasons)


@patch("app.core.orats.orats_core_client.fetch_core_snapshot")
def test_build_equity_snapshot_missing_fields_have_reason(mock_fetch):
    mock_fetch.return_value = {"ticker": "AAPL"}
    snapshot = build_equity_snapshot_from_core("AAPL", token="test-token")
    assert snapshot.ticker == "AAPL"
    assert len(snapshot.missing_fields) >= 1
    for name in snapshot.missing_fields:
        assert name in snapshot.missing_reasons
        assert REASON_NOT_PROVIDED in snapshot.missing_reasons[name] or "ORATS" in snapshot.missing_reasons[name]


@patch("requests.get")
def test_fetch_core_snapshot_parses_data_array(mock_get):
    from app.core.orats.orats_core_client import fetch_core_snapshot

    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"data": [{"stkVolu": 1, "pxCls": 100}]}
    mock_get.return_value.text = ""
    out = fetch_core_snapshot("AAPL", ["stkVolu", "pxCls"], "token")
    assert out.get("stkVolu") == 1
    assert out.get("pxCls") == 100


@patch("requests.get")
def test_fetch_core_snapshot_raises_on_empty_data(mock_get):
    from app.core.orats.orats_core_client import fetch_core_snapshot, OratsCoreError

    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"data": []}
    mock_get.return_value.text = "[]"
    with pytest.raises(OratsCoreError):
        fetch_core_snapshot("AAPL", ["stkVolu"], "token")
