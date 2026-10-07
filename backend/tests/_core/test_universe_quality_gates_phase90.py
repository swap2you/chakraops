# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 9.0: Universe quality gates."""

from __future__ import annotations

import pytest

from app.core.universe.universe_quality_gates import GateDecision, evaluate_universe_quality


def _default_config():
    return {
        "enabled": True,
        "max_spread_pct": 0.012,
        "min_price_usd": 8.0,
        "max_price_usd": 600.0,
        "min_avg_volume": 800_000,
        "min_option_oi": 500,
        "min_option_volume": 50,
        "max_option_bidask_pct": 0.10,
        "data_stale_days_block": 2,
    }


def test_gates_disabled_returns_pass():
    """When gates disabled globally or per symbol, returns PASS."""
    cfg = _default_config()
    cfg["enabled"] = False
    d = evaluate_universe_quality("AAPL", {}, None, {}, cfg, None)
    assert d.status == "PASS"
    assert not d.reasons


def test_missing_price_skips():
    """When price missing, SKIP with missing_price."""
    cfg = _default_config()
    ds = {"required_data_missing": [], "required_data_stale": []}
    d = evaluate_universe_quality("AAPL", {}, None, ds, cfg, None)
    assert d.status == "SKIP"
    assert "missing_price" in d.reasons


def test_price_below_min_skips():
    """When price < min_price_usd, SKIP."""
    cfg = _default_config()
    ds = {"required_data_missing": [], "required_data_stale": []}
    core = {"price": 5.0, "bid": 4.9, "ask": 5.1}
    d = evaluate_universe_quality("AAPL", core, None, ds, cfg, None)
    assert d.status == "SKIP"
    assert "price_below_min" in d.reasons


def test_underlying_spread_too_wide_skips():
    """When bid/ask spread > max_spread_pct, SKIP."""
    cfg = _default_config()
    ds = {"required_data_missing": [], "required_data_stale": []}
    core = {"price": 100.0, "bid": 98.0, "ask": 102.0}  # 4% spread > 1.2%
    d = evaluate_universe_quality("AAPL", core, None, ds, cfg, None)
    assert d.status == "SKIP"
    assert "wide_spread" in d.reasons


def test_data_missing_skips():
    """When required_data_missing non-empty, SKIP."""
    cfg = _default_config()
    ds = {"required_data_missing": ["volume"], "required_data_stale": []}
    core = {"price": 100.0}
    d = evaluate_universe_quality("AAPL", core, None, ds, cfg, None)
    assert d.status == "SKIP"
    assert "required_data_missing" in d.reasons


def test_data_stale_skips():
    """When required_data_stale non-empty, SKIP."""
    cfg = _default_config()
    ds = {"required_data_missing": [], "required_data_stale": ["quote_date"]}
    core = {"price": 100.0}
    d = evaluate_universe_quality("AAPL", core, None, ds, cfg, None)
    assert d.status == "SKIP"
    assert "stale_data" in d.reasons


def test_avg_volume_low_skips_when_present():
    """When avg_stock_volume_20d present and < min, SKIP."""
    cfg = _default_config()
    ds = {"required_data_missing": [], "required_data_stale": []}
    core = {"price": 100.0, "avg_stock_volume_20d": 500_000}
    d = evaluate_universe_quality("AAPL", core, None, ds, cfg, None)
    assert d.status == "SKIP"
    assert "low_avg_volume" in d.reasons


def test_option_spread_too_wide_skips_when_chain_provided():
    """When chain_liquidity provided and option spread > max, SKIP."""
    cfg = _default_config()
    ds = {"required_data_missing": [], "required_data_stale": []}
    core = {"price": 100.0}
    chain = {"option_bid": 4.0, "option_ask": 6.0, "option_mid": 5.0}  # 40% spread
    d = evaluate_universe_quality("AAPL", core, chain, ds, cfg, None)
    assert d.status == "SKIP"
    assert "wide_option_spread" in d.reasons


def test_option_oi_low_skips():
    """When chain provided and option_oi < min, SKIP."""
    cfg = _default_config()
    ds = {"required_data_missing": [], "required_data_stale": []}
    core = {"price": 100.0}
    chain = {"option_bid": 4.9, "option_ask": 5.1, "option_mid": 5.0, "option_oi": 100}
    d = evaluate_universe_quality("AAPL", core, chain, ds, cfg, None)
    assert d.status == "SKIP"
    assert "low_oi" in d.reasons


def test_option_volume_low_skips():
    """When chain provided and option_volume < min, SKIP."""
    cfg = _default_config()
    ds = {"required_data_missing": [], "required_data_stale": []}
    core = {"price": 100.0}
    chain = {"option_bid": 4.9, "option_ask": 5.1, "option_mid": 5.0, "option_oi": 1000, "option_volume": 10}
    d = evaluate_universe_quality("AAPL", core, chain, ds, cfg, None)
    assert d.status == "SKIP"
    assert "low_option_volume" in d.reasons


def test_symbol_override_disables_gates():
    """Per-symbol override enabled=false -> PASS."""
    cfg = _default_config()
    override = {"enabled": False}
    ds = {"required_data_missing": [], "required_data_stale": []}
    core = {"price": 5.0}
    d = evaluate_universe_quality("TSLA", core, None, ds, cfg, override)
    assert d.status == "PASS"


def test_symbol_override_thresholds_applied():
    """Per-symbol override max_option_bidask_pct=0.12 relaxes option spread."""
    cfg = _default_config()
    override = {"max_option_bidask_pct": 0.12}
    ds = {"required_data_missing": [], "required_data_stale": []}
    core = {"price": 100.0}
    chain = {"option_bid": 4.4, "option_ask": 4.95, "option_mid": 4.675, "option_oi": 1000, "option_volume": 100}
    d = evaluate_universe_quality("TSLA", core, chain, ds, cfg, override)
    assert d.status == "PASS"


def test_pass_with_good_data():
    """Good underlying data and no chain -> PASS."""
    cfg = _default_config()
    ds = {"required_data_missing": [], "required_data_stale": []}
    core = {"price": 150.0, "bid": 149.5, "ask": 150.5, "avg_stock_volume_20d": 2_000_000}
    d = evaluate_universe_quality("AAPL", core, None, ds, cfg, None)
    assert d.status == "PASS"
    assert not d.reasons


def test_gate_filtering_excludes_skip_symbols():
    """Integration: Gate filtering logic excludes SKIP symbols from evaluation list."""
    from app.core.universe.universe_quality_gates import evaluate_universe_quality, GateDecision

    symbols = ["A", "B", "C"]
    cfg = _default_config()
    ds_ok = {"required_data_missing": [], "required_data_stale": []}
    core_ok = {"price": 100.0, "bid": 99.5, "ask": 100.5, "avg_stock_volume_20d": 2_000_000}
    core_bad = {"price": 5.0}

    symbols_to_evaluate = []
    for sym in symbols:
        core = core_ok if sym != "B" else core_bad
        d = evaluate_universe_quality(sym, core, None, ds_ok, cfg, None)
        if d.status == "PASS":
            symbols_to_evaluate.append(sym)

    assert "A" in symbols_to_evaluate
    assert "B" not in symbols_to_evaluate
    assert "C" in symbols_to_evaluate
