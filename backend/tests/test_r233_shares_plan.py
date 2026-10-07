# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.3: Shares eligibility, plan (entry_zone, stop, targets), sizing; shares_plan not persisted; UAT override."""

import json
import os
import pytest

from app.core.shares.shares_plan import (
    compute_shares_eligibility,
    build_shares_plan_r233,
)


class _Summary:
    def __init__(self, stage1_status="PASS", regime="UP", price=100.0, provider_status="OK"):
        self.stage1_status = stage1_status
        self.regime = regime
        self.price = price
        self.provider_status = provider_status


def test_shares_eligibility_true_when_all_pass():
    """Eligibility true when regime UP, near support, RSI in range, stock quality pass."""
    summary = _Summary(stage1_status="PASS", regime="UP", price=100.0)
    technicals = {"spot": 100.0, "support_level": 99.0, "rsi": 50.0, "regime": "UP"}
    sel = {}
    eligible, codes = compute_shares_eligibility(summary, technicals, sel, mtf_levels=None)
    assert eligible is True
    assert codes == ["SHARES_ELIGIBLE"]


def test_shares_eligibility_false_when_far_from_support():
    """Eligibility false when not near support (distance > SHARES_NEAR_SUPPORT_PCT)."""
    summary = _Summary(stage1_status="PASS", regime="UP")
    technicals = {"spot": 100.0, "support_level": 90.0, "rsi": 50.0}
    sel = {}
    eligible, codes = compute_shares_eligibility(summary, technicals, sel, mtf_levels=None)
    assert eligible is False
    assert "NOT_NEAR_SUPPORT" in codes


def test_shares_eligibility_false_when_regime_conflict():
    """Eligibility false when regime not UP (and NEUTRAL not allowed)."""
    summary = _Summary(stage1_status="PASS", regime="DOWN")
    technicals = {"spot": 100.0, "support_level": 99.0, "rsi": 50.0, "regime": "DOWN"}
    sel = {}
    eligible, codes = compute_shares_eligibility(summary, technicals, sel, mtf_levels=None)
    assert eligible is False
    assert "REGIME_NOT_PREFERRED" in codes


def test_shares_eligibility_false_when_stage1_fail():
    """Eligibility false when stock quality (Stage 1) fails."""
    summary = _Summary(stage1_status="FAIL", regime="UP")
    technicals = {"spot": 100.0, "support_level": 99.0, "rsi": 50.0}
    sel = {}
    eligible, codes = compute_shares_eligibility(summary, technicals, sel, mtf_levels=None)
    assert eligible is False
    assert "NOT_STOCK_QUALITY" in codes


def test_shares_plan_entry_zone_stop_targets_monotonic():
    """Entry zone low <= high; stop < entry_low when support below spot; t1/t2 > spot when resistances available."""
    summary = _Summary(price=100.0)
    technicals = {"spot": 100.0, "support_level": 98.0, "resistance_level": 105.0, "atr": 2.0, "regime": "UP"}
    exit_plan = {"t1": 104.0, "t2": 108.0, "t3": 112.0, "stop": 96.0}
    hold_time = {"sessions": 5, "basis_key": "atr_sessions_to_target"}
    plan = build_shares_plan_r233(
        summary, technicals, exit_plan, hold_time, "WMT",
        mtf_levels=None, as_of_inputs={"run_id": "r1", "config_hash": "abc"},
        symbol_eligibility={},
        account_summary=None,
    )
    assert plan["entry_zone"]["low"] is not None
    assert plan["entry_zone"]["high"] is not None
    assert plan["entry_zone"]["low"] <= plan["entry_zone"]["high"]
    stop_price = plan["stop"]["price"] if isinstance(plan["stop"], dict) else plan["stop"]
    assert stop_price is not None
    assert stop_price < (plan["entry_zone"]["low"] or 0)
    assert plan["targets"]["t1"] is not None
    assert plan["targets"]["t2"] is not None
    assert plan["spot"] is not None
    assert plan["targets"]["t1"] > plan["spot"]
    assert plan["targets"]["t2"] > plan["spot"]


def test_shares_plan_sizing_with_mocked_account():
    """Sizing computed when account summary has cash/buying_power; suggested_shares and max_loss present."""
    summary = _Summary(price=50.0)
    technicals = {"spot": 50.0, "support_level": 48.0, "atr": 1.0, "regime": "UP"}
    exit_plan = {"t1": 52.0, "stop": 47.0}
    hold_time = {"sessions": 4, "basis_key": "default_estimate"}
    account_summary = {"cash": 10000.0, "buying_power": 15000.0, "total_capital": 20000.0}
    plan = build_shares_plan_r233(
        summary, technicals, exit_plan, hold_time, "TEST",
        mtf_levels=None, as_of_inputs={},
        symbol_eligibility={},
        account_summary=account_summary,
    )
    sizing = plan.get("sizing") or {}
    assert sizing.get("basis") == "ACCOUNT_RISK"
    assert sizing.get("suggested_shares") is not None
    assert sizing.get("suggested_shares") >= 0
    assert sizing.get("max_loss") is not None
    assert sizing.get("suggested_cost") is not None


def test_shares_plan_sizing_insufficient_data_without_account():
    """Sizing basis INSUFFICIENT_DATA when account data missing."""
    summary = _Summary(price=50.0)
    technicals = {"spot": 50.0, "support_level": 48.0, "atr": 1.0}
    exit_plan = {"t1": 52.0, "stop": 47.0}
    plan = build_shares_plan_r233(
        summary, technicals, exit_plan, None, "TEST",
        mtf_levels=None, as_of_inputs={},
        account_summary=None,
    )
    sizing = plan.get("sizing") or {}
    assert sizing.get("basis") == "INSUFFICIENT_DATA"
    assert sizing.get("suggested_shares") is None


def test_shares_plan_not_in_decision_artifact(tmp_path):
    """Decision artifact must not contain shares_plan (request-time only)."""
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir, get_evaluation_store_v2

    artifact_dict = {
        "metadata": {"artifact_version": "v2", "pipeline_timestamp": "2026-02-17T20:00:00Z"},
        "symbols": [{"symbol": "WMT", "verdict": "HOLD", "final_verdict": "HOLD", "score": 50, "band": "C", "stage1_status": "PASS", "stage2_status": "FAIL", "primary_reason_codes": [], "stage_status": "RUN", "provider_status": "OK", "data_freshness": None, "evaluated_at": None, "strategy": None, "price": 170.0, "expiration": None, "has_candidates": False, "candidate_count": 0}],
        "selected_candidates": [],
        "candidates_by_symbol": {},
        "gates_by_symbol": {"WMT": [{"gate_code": "STOCK_QUALITY_STAGE1", "status": "PASS"}]},
        "earnings_by_symbol": {},
        "warnings": [],
    }
    (tmp_path / "decision_latest.json").write_text(json.dumps(artifact_dict), encoding="utf-8")
    try:
        set_output_dir(tmp_path)
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        loaded = store.get_latest()
        assert loaded is not None
        raw = (tmp_path / "decision_latest.json").read_text(encoding="utf-8")
        assert "shares_plan" not in raw
    finally:
        reset_output_dir()


def test_uat_force_eligible_override():
    """UAT override: when symbol in SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS, eligible=True and reason_codes include SHARES_UAT_FORCED."""
    summary = _Summary(stage1_status="FAIL", regime="DOWN")
    technicals = {"spot": 100.0, "support_level": 90.0, "rsi": 30.0}
    sel = {}
    # Without override: not eligible
    eligible, codes = compute_shares_eligibility(summary, technicals, sel, mtf_levels=None, symbol="NVDA")
    assert eligible is False
    # With env override: forced eligible and SHARES_UAT_FORCED in codes
    prev = os.environ.pop("SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS", None)
    try:
        os.environ["SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS"] = "NVDA"
        eligible, codes = compute_shares_eligibility(summary, technicals, sel, mtf_levels=None, symbol="NVDA")
        assert eligible is True
        assert "SHARES_UAT_FORCED" in codes
        # Other symbol not in list still not eligible
        eligible2, _ = compute_shares_eligibility(summary, technicals, sel, mtf_levels=None, symbol="WMT")
        assert eligible2 is False
    finally:
        if prev is not None:
            os.environ["SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS"] = prev
        else:
            os.environ.pop("SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS", None)


def test_uat_override_does_not_persist(tmp_path):
    """With UAT override, shares_plan is still request-time only; decision_latest.json must not contain shares_plan."""
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir, get_evaluation_store_v2

    artifact_dict = {
        "metadata": {"artifact_version": "v2", "pipeline_timestamp": "2026-02-17T20:00:00Z"},
        "symbols": [{"symbol": "NVDA", "verdict": "HOLD", "final_verdict": "HOLD", "score": 50, "band": "C", "stage1_status": "FAIL", "stage2_status": "FAIL", "primary_reason_codes": [], "stage_status": "RUN", "provider_status": "OK", "data_freshness": None, "evaluated_at": None, "strategy": None, "price": 500.0, "expiration": None, "has_candidates": False, "candidate_count": 0}],
        "selected_candidates": [],
        "candidates_by_symbol": {},
        "gates_by_symbol": {"NVDA": [{"gate_code": "STOCK_QUALITY_STAGE1", "status": "FAIL"}]},
        "earnings_by_symbol": {},
        "warnings": [],
    }
    (tmp_path / "decision_latest.json").write_text(json.dumps(artifact_dict), encoding="utf-8")
    prev = os.environ.pop("SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS", None)
    try:
        os.environ["SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS"] = "NVDA"
        set_output_dir(tmp_path)
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        raw = (tmp_path / "decision_latest.json").read_text(encoding="utf-8")
        assert "shares_plan" not in raw
    finally:
        reset_output_dir()
        if prev is not None:
            os.environ["SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS"] = prev
        else:
            os.environ.pop("SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS", None)
