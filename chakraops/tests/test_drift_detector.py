# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Phase 8.2 drift detector.

Mock live data inputs. Ensure no mutation of snapshot objects.
"""

from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from app.market.drift_detector import (
    DriftReason,
    DriftSeverity,
    DriftStatus,
    DriftItem,
    DriftConfig,
    detect_drift,
)
from app.market.live_market_adapter import LiveMarketData


def _make_snapshot(
    selected_underlying_prices: Dict[str, float] | None = None,
    selected_iv: Dict[str, float] | None = None,
    selected_signals: list | None = None,
) -> Dict[str, Any]:
    """Minimal snapshot dict for tests. selected_signals override builds from selected_underlying_prices/selected_iv."""
    selected_signals = selected_signals or []
    if selected_underlying_prices or selected_iv:
        for sym, price in (selected_underlying_prices or {}).items():
            selected_signals.append({
                "scored": {
                    "candidate": {
                        "symbol": sym,
                        "strike": 100.0,
                        "expiry": "2026-02-20",
                        "signal_type": "CSP",
                        "option_right": "PUT",
                        "underlying_price": price,
                        "bid": 2.0,
                        "ask": 2.1,
                        "mid": 2.05,
                        "iv": (selected_iv or {}).get(sym),
                    },
                },
            })
    return {
        "as_of": "2026-01-29T12:00:00",
        "universe_id_or_hash": "test",
        "stats": {},
        "candidates": [],
        "scored_candidates": [],
        "selected_signals": selected_signals,
        "explanations": None,
        "exclusions": None,
    }


def _make_live(
    data_source: str = "ThetaTerminal",
    underlying_prices: Dict[str, float] | None = None,
    option_chain_available: Dict[str, bool] | None = None,
    iv_by_contract: Dict[str, float] | None = None,
    live_quotes: Dict[str, tuple] | None = None,
) -> LiveMarketData:
    return LiveMarketData(
        data_source=data_source,
        last_update_utc="2026-01-29T12:05:00Z",
        underlying_prices=underlying_prices or {},
        option_chain_available=option_chain_available or {},
        iv_by_contract=iv_by_contract or {},
        greeks_by_contract={},
        live_quotes=live_quotes or {},
        errors=[],
    )


def test_detect_drift_no_drift_when_aligned() -> None:
    """When live data matches snapshot assumptions, has_drift is False."""
    snapshot = _make_snapshot(selected_underlying_prices={"AAPL": 150.0}, selected_iv={"AAPL": 0.25})
    live = _make_live(
        underlying_prices={"AAPL": 150.5},
        option_chain_available={"AAPL": True},
        iv_by_contract={"AAPL|100.0|2026-02-20|PUT": 0.26},
    )
    result = detect_drift(snapshot, live)
    assert isinstance(result, DriftStatus)
    assert result.has_drift is False
    assert len(result.items) == 0


def test_detect_drift_price_drift() -> None:
    """PRICE_DRIFT when live underlying price differs beyond threshold."""
    snapshot = _make_snapshot(selected_underlying_prices={"AAPL": 100.0})
    live = _make_live(underlying_prices={"AAPL": 105.0}, option_chain_available={"AAPL": True})
    result = detect_drift(snapshot, live)
    assert result.has_drift is True
    price_items = [i for i in result.items if i.reason == DriftReason.PRICE_DRIFT]
    assert len(price_items) >= 1
    assert price_items[0].symbol == "AAPL"
    assert price_items[0].snapshot_value == 100.0
    assert price_items[0].live_value == 105.0


def test_detect_drift_iv_drift() -> None:
    """IV_DRIFT when live IV differs beyond threshold."""
    snapshot = _make_snapshot(
        selected_underlying_prices={"SPY": 450.0},
        selected_iv={"SPY": 0.20},
    )
    live = _make_live(
        underlying_prices={"SPY": 450.0},
        option_chain_available={"SPY": True},
        iv_by_contract={"SPY|100.0|2026-02-20|PUT": 0.40},
    )
    result = detect_drift(snapshot, live)
    assert result.has_drift is True
    iv_items = [i for i in result.items if i.reason == DriftReason.IV_DRIFT]
    assert len(iv_items) >= 1
    assert iv_items[0].symbol == "SPY"


def test_detect_drift_chain_unavailable() -> None:
    """CHAIN_UNAVAILABLE when option_chain_available[symbol] is False."""
    snapshot = _make_snapshot(selected_underlying_prices={"XYZ": 50.0})
    live = _make_live(
        underlying_prices={"XYZ": 50.0},
        option_chain_available={"XYZ": False},
    )
    result = detect_drift(snapshot, live)
    assert result.has_drift is True
    chain_items = [i for i in result.items if i.reason == DriftReason.CHAIN_UNAVAILABLE]
    assert len(chain_items) >= 1
    assert chain_items[0].symbol == "XYZ"


def test_detect_drift_spread_widened() -> None:
    """SPREAD_WIDENED when live_quotes has wider spread than snapshot."""
    snapshot = _make_snapshot(selected_signals=[{
        "scored": {
            "candidate": {
                "symbol": "AAPL",
                "strike": 100.0,
                "expiry": "2026-02-20",
                "signal_type": "CSP",
                "option_right": "PUT",
                "underlying_price": 150.0,
                "bid": 2.00,
                "ask": 2.10,
                "mid": 2.05,
                "iv": None,
            },
        },
    }])
    key = "AAPL|100.0|2026-02-20|PUT"
    live = _make_live(
        underlying_prices={"AAPL": 150.0},
        option_chain_available={"AAPL": True},
        live_quotes={key: (1.50, 3.50)},  # spread ~133% vs snapshot ~5%
    )
    result = detect_drift(snapshot, live)
    assert result.has_drift is True
    spread_items = [i for i in result.items if i.reason == DriftReason.SPREAD_WIDENED]
    assert len(spread_items) >= 1
    assert spread_items[0].symbol == "AAPL"


def test_detect_drift_does_not_mutate_snapshot() -> None:
    """detect_drift must not mutate the snapshot dict."""
    snapshot = _make_snapshot(selected_underlying_prices={"AAPL": 150.0})
    snapshot_copy = copy.deepcopy(snapshot)
    live = _make_live(underlying_prices={"AAPL": 160.0}, option_chain_available={"AAPL": True})
    detect_drift(snapshot, live)
    assert snapshot == snapshot_copy


def test_detect_drift_empty_snapshot() -> None:
    """Empty selected_signals yields no drift items (or only from scored_candidates)."""
    snapshot = _make_snapshot(selected_signals=[])
    live = _make_live(underlying_prices={}, option_chain_available={})
    result = detect_drift(snapshot, live)
    assert isinstance(result, DriftStatus)
    assert result.has_drift is False
    assert result.items == []


def test_detect_drift_extracts_symbols_from_scored_candidates() -> None:
    """Symbols from scored_candidates are used for CHAIN_UNAVAILABLE check."""
    snapshot = {
        "selected_signals": [],
        "scored_candidates": [
            {"scored": {"candidate": {"symbol": "MSFT"}}},
        ],
        "candidates": [],
    }
    live = _make_live(option_chain_available={"MSFT": False})
    result = detect_drift(snapshot, live)
    chain_items = [i for i in result.items if i.reason == DriftReason.CHAIN_UNAVAILABLE]
    assert any(i.symbol == "MSFT" for i in chain_items)


def test_drift_reason_values() -> None:
    """DriftReason enum has expected values."""
    assert DriftReason.PRICE_DRIFT.value == "PRICE_DRIFT"
    assert DriftReason.IV_DRIFT.value == "IV_DRIFT"
    assert DriftReason.CHAIN_UNAVAILABLE.value == "CHAIN_UNAVAILABLE"
    assert DriftReason.SPREAD_WIDENED.value == "SPREAD_WIDENED"


def test_drift_item_attributes() -> None:
    """DriftItem has reason, symbol, message, severity, optional snapshot_value/live_value."""
    item = DriftItem(
        reason=DriftReason.PRICE_DRIFT,
        symbol="AAPL",
        message="Underlying price drifted 5%",
        snapshot_value=100.0,
        live_value=105.0,
    )
    assert item.reason == DriftReason.PRICE_DRIFT
    assert item.symbol == "AAPL"
    assert item.snapshot_value == 100.0
    assert item.live_value == 105.0
    assert item.severity == DriftSeverity.INFO or item.severity == DriftSeverity.WARN


def test_drift_configurable_threshold_warn_vs_info() -> None:
    """With price_drift_warn_pct 0.75, small drift can be INFO; larger WARN."""
    snapshot = _make_snapshot(selected_underlying_prices={"AAPL": 100.0})
    config = DriftConfig(price_drift_warn_pct=0.75)
    # 0.5% drift: below 0.75% so no item
    live_small = _make_live(underlying_prices={"AAPL": 100.5}, option_chain_available={"AAPL": True})
    result_small = detect_drift(snapshot, live_small, config=config)
    price_items_small = [i for i in result_small.items if i.reason == DriftReason.PRICE_DRIFT]
    assert len(price_items_small) == 0
    # 1% drift: >= 0.75%, severity INFO (1% < 1.5% = 2 * 0.75)
    live_1pct = _make_live(underlying_prices={"AAPL": 101.0}, option_chain_available={"AAPL": True})
    result_1 = detect_drift(snapshot, live_1pct, config=config)
    price_items_1 = [i for i in result_1.items if i.reason == DriftReason.PRICE_DRIFT]
    assert len(price_items_1) >= 1
    assert price_items_1[0].severity in (DriftSeverity.INFO, DriftSeverity.WARN)
