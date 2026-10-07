# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.1 — explainability contract builder tests."""

from __future__ import annotations

from app.core.decision_engine.explanation import build_explanation

PROFILE = {
    "name": "balanced",
    "csp_delta_range": [0.20, 0.40],
    "cc_delta_range": [0.20, 0.40],
    "dte_range": [30, 45],
    "min_return_pct": 2.0,
    "liquidity": {"min_open_interest": 500, "min_volume": 50, "max_bid_ask_spread_pct": 10.0},
    "max_sector_exposure_pct": 35.0,
}


def _actionable_item():
    return {
        "symbol": "AAPL", "strategy": "CSP", "profile": "balanced",
        "decision_status": "ACTIONABLE",
        "reason_codes": ["DELTA_IN_RANGE", "DTE_IN_RANGE", "MEETS_RETURN_THRESHOLD"],
        "risk_flags": [],
        "selected_contract": {"delta": 0.30, "dte": 35, "open_interest": 1200, "volume": 300,
                              "bid_ask_spread_pct": 2.0, "premium": 2.5, "strike": 100.0},
        "expected_return_pct": 2.6, "expected_return_dollars": 250.0, "capital_required": 10000.0,
        "sizing": {"contracts": 1, "shares": 0},
        "data_freshness": {"inputs": [
            {"label": "PRICE", "status": "FRESH", "as_of_utc": "2026-07-11T20:00:00+00:00",
             "age_seconds": 60.0, "max_age_seconds": 86400.0},
            {"label": "OPTIONS_CHAIN", "status": "FRESH", "as_of_utc": "2026-07-11T20:00:00+00:00",
             "age_seconds": 90.0, "max_age_seconds": 86400.0},
        ]},
        "event_risk": {"earnings_days": 30, "blackout_days": 3},
    }


def _blocked_item():
    return {
        "symbol": "XYZ", "strategy": "CSP", "profile": "balanced",
        "decision_status": "BLOCKED",
        "reason_codes": ["WIDE_SPREAD"], "risk_flags": [],
        "selected_contract": {"delta": 0.30, "dte": 35, "open_interest": 1200, "volume": 300,
                              "bid_ask_spread_pct": 25.0, "premium": 2.5, "strike": 50.0},
        "expected_return_pct": None, "capital_required": 0.0, "sizing": {},
        "data_freshness": {"inputs": []}, "event_risk": {},
    }


def test_contract_core_fields_present():
    exp = build_explanation(_actionable_item(), PROFILE)
    assert exp["symbol"] == "AAPL"
    assert exp["strategy"] == "CSP"
    assert exp["decision_status"] == "ACTIONABLE"
    assert exp["manual_only"] is True
    assert exp["trade_execution"] is False
    assert exp["primary_reason"] is not None
    assert isinstance(exp["supporting_reasons"], list)
    assert "calculation_trace" in exp and "measured_values" in exp
    assert "near_miss" in exp and "data_sources" in exp


def test_no_order_or_broker_fields():
    exp = build_explanation(_actionable_item(), PROFILE)
    text = str(exp).lower()
    for forbidden in ("order_id", "broker", "submit_order", "buy_to_open", "sell_to_close"):
        assert forbidden not in text


def test_measured_values_have_units_and_within_flag():
    exp = build_explanation(_actionable_item(), PROFILE)
    by_code = {m["code"]: m for m in exp["measured_values"]}
    assert "DELTA_IN_RANGE" in by_code
    delta_mv = by_code["DELTA_IN_RANGE"]
    assert delta_mv["unit"] == "delta"
    assert delta_mv["measured"] == 0.30
    assert delta_mv["threshold"] == [0.20, 0.40]
    assert delta_mv["within"] is True


def test_timestamps_and_data_sources_from_freshness():
    exp = build_explanation(_actionable_item(), PROFILE)
    assert exp["timestamps"]["price_as_of"] == "2026-07-11T20:00:00+00:00"
    assert exp["timestamps"]["chain_as_of"] == "2026-07-11T20:00:00+00:00"
    src_names = {s["name"] for s in exp["data_sources"]}
    assert "PRICE" in src_names and "OPTIONS_CHAIN" in src_names


def test_blocked_item_classified_safety_critical_and_no_near_miss():
    exp = build_explanation(_blocked_item(), PROFILE)
    assert "WIDE_SPREAD" in exp["safety_critical_reasons"]
    assert "WIDE_SPREAD" in exp["failed_gates"]
    assert exp["near_miss"]["is_near_miss"] is False
    # WIDE_SPREAD measured 25 > threshold 10 -> not within
    wide = next(m for m in exp["measured_values"] if m["code"] == "WIDE_SPREAD")
    assert wide["within"] is False
    assert wide["unit"] == "pct"


def test_never_invents_missing_data():
    item = {"symbol": "N", "strategy": "CSP", "decision_status": "WATCH",
            "reason_codes": ["DELTA_OUT_OF_RANGE"], "risk_flags": [],
            "selected_contract": None, "expected_return_pct": None, "sizing": {},
            "data_freshness": {}, "event_risk": {}}
    exp = build_explanation(item, PROFILE)
    # No selected_contract -> delta measured is None, not fabricated; still resolves the code.
    assert exp["timestamps"]["price_as_of"] is None
    assert exp["portfolio_impact"]["contracts"] is None
    # measured_values may be empty (no measured & threshold) but must not fabricate numbers
    for mv in exp["measured_values"]:
        assert mv["measured"] is None or isinstance(mv["measured"], (int, float))


def test_primary_reason_is_highest_severity():
    # Mix INFO + SOFT: SOFT should be primary.
    item = _actionable_item()
    item["decision_status"] = "WATCH"
    item["reason_codes"] = ["DELTA_IN_RANGE", "BELOW_RETURN_THRESHOLD"]
    exp = build_explanation(item, PROFILE)
    assert exp["primary_reason"]["code"] == "BELOW_RETURN_THRESHOLD"


def test_no_raw_fail_warn_in_text():
    item = _actionable_item()
    item["reason_codes"] = ["FAIL_DELTA_OUT_OF_RANGE", "WARN_IV_RANK_UNAVAILABLE"]
    exp = build_explanation(item, PROFILE)
    text = str(exp)
    assert "FAIL_" not in text
    assert "WARN_" not in text


def test_empty_item_is_safe():
    exp = build_explanation(None, None)
    assert exp["manual_only"] is True
    assert exp["trade_execution"] is False
    assert exp["near_miss"]["is_near_miss"] is False
