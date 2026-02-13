# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.1: Position evaluator and ledger. No broker; deterministic."""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core.positions.position_evaluator import (
    EXIT_HOLD,
    EXIT_NOW,
    EXIT_ROLL_SUGGESTED,
    EXIT_TAKE_PROFIT,
    evaluate_position,
)


def _pos(overrides=None, **kwargs):
    d = {
        "position_id": "test-uuid",
        "symbol": "SPY",
        "mode": "CSP",
        "entry_date": (date.today() - timedelta(days=10)).isoformat(),
        "expiration": (date.today() + timedelta(days=35)).isoformat(),
        "strike": 500.0,
        "contracts": 1,
        "entry_premium": 10.0,
        "entry_spot": 498.0,
        "notes": "",
        "status": "OPEN",
    }
    d.update(kwargs)
    if overrides:
        d.update(overrides)
    return d


def _exit_plan(T1=505, T2=510, panic_flag=False, regime_daily="UP"):
    return {
        "enabled": True,
        "mode": "CSP",
        "structure_plan": {"T1": T1, "T2": T2, "T3": None, "stop_hint_price": None},
        "time_plan": {"dte_soft_exit": 14, "dte_hard_exit": 7, "dte": 35},
        "panic_plan": {"panic_flag": panic_flag, "panic_reason": "regime_flip" if panic_flag else None},
        "inputs": {"regime_daily": regime_daily},
    }


def test_75_percent_premium_exit_now():
    """Premium capture >= 75% → EXIT_NOW."""
    # entry 10, mid 2.5 → capture (10-2.5)/10 = 0.75
    pos = _pos()
    ep = _exit_plan()
    ev = evaluate_position(pos, 500.0, 2.0, 3.0, ep, date.today())
    assert ev["exit_signal"] == EXIT_NOW
    assert ev["exit_reason"] == "premium_75_target"
    assert ev["premium_capture_pct"] == 0.75


def test_60_percent_premium_structure_strong_hold():
    """60% premium + spot < T2 and regime favorable → HOLD."""
    # premium 60%, spot below T2, regime UP (favorable for CSP)
    pos = _pos()
    # bid+ask mid such that capture = 0.60: (10 - mid)/10 = 0.60 → mid = 4
    ep = _exit_plan(T1=520, T2=530)
    ev = evaluate_position(pos, 500.0, 3.5, 4.5, ep, date.today())  # mid=4, capture=0.60
    assert ev["exit_signal"] == EXIT_HOLD
    assert ev["exit_reason"] == "ride_zone_60_regime_ok"
    assert ev["premium_capture_pct"] == 0.60


def test_60_percent_premium_structure_weak_take_profit():
    """60% premium but spot >= T2 (structure weak for holding) → TAKE_PROFIT."""
    pos = _pos()
    ep = _exit_plan(T1=495, T2=498)  # T2=498, spot 500 >= T2 so hit_T2
    ev = evaluate_position(pos, 500.0, 3.5, 4.5, ep, date.today())
    # hit_T2 is True (spot 500 >= T2 498), so we'd get EXIT_NOW from structure T2 before we get to 60% rule.
    # So we need a case where we have 60% but not hit_T2 and not regime favorable. E.g. regime DOWN.
    ep2 = _exit_plan(T1=520, T2=530, regime_daily="DOWN")
    ev2 = evaluate_position(pos, 500.0, 3.5, 4.5, ep2, date.today())
    assert ev2["exit_signal"] == EXIT_TAKE_PROFIT
    assert ev2["exit_reason"] == "premium_60_take_profit"


def test_dte_7_exit_now():
    """dte <= 7 → EXIT_NOW."""
    exp = date.today() + timedelta(days=5)
    pos = _pos(expiration=exp.isoformat())
    ep = _exit_plan()
    ev = evaluate_position(pos, 500.0, 5.0, 6.0, ep, date.today())
    assert ev["dte"] == 5
    assert ev["exit_signal"] == EXIT_NOW
    assert ev["exit_reason"] == "dte_hard_exit"


def test_dte_14_roll_suggested():
    """dte <= 14 but > 7 → ROLL_SUGGESTED."""
    exp = date.today() + timedelta(days=10)
    pos = _pos(expiration=exp.isoformat())
    ep = _exit_plan()
    # premium below 75% so we don't hit premium_75; dte 10 triggers soft
    ev = evaluate_position(pos, 500.0, 6.0, 7.0, ep, date.today())
    assert ev["dte"] == 10
    assert ev["exit_signal"] == EXIT_ROLL_SUGGESTED
    assert ev["exit_reason"] == "dte_soft_roll"


def test_panic_flag_exit_now():
    """panic_plan.panic_flag true → EXIT_NOW."""
    pos = _pos()
    ep = _exit_plan(panic_flag=True)
    ev = evaluate_position(pos, 500.0, 8.0, 9.0, ep, date.today())
    assert ev["exit_signal"] == EXIT_NOW
    assert ev["exit_reason"] == "panic_regime_flip"
    assert "panic" in ev["risk_flags"]


def test_no_mutation_of_position():
    """evaluate_position does not mutate the position dict."""
    pos = _pos()
    pos_id = id(pos)
    pos_copy = dict(pos)
    ep = _exit_plan()
    evaluate_position(pos, 500.0, 4.0, 5.0, ep, date.today())
    assert id(pos) == pos_id
    assert pos == pos_copy


def test_ledger_load_save_add_close(tmp_path: Path):
    """Position ledger: load empty, add, load, close, load returns empty open list."""
    from app.core.positions.position_ledger import (
        load_open_positions,
        save_open_positions,
        add_position,
        close_position,
    )
    ledger = tmp_path / "open_positions.json"
    assert load_open_positions(ledger) == []
    add_position("SPY", "CSP", "2026-01-01", "2026-03-20", 500.0, 1, 10.0, 498.0, "", ledger_path=ledger)
    open_list = load_open_positions(ledger)
    assert len(open_list) == 1
    assert open_list[0]["symbol"] == "SPY"
    assert open_list[0].get("option_type") == "PUT"
    pid = open_list[0]["position_id"]
    close_position(pid, ledger)
    assert load_open_positions(ledger) == []


def test_missing_bid_ask_premium_none_risk_flag_data_missing():
    """Missing bid/ask -> premium_capture_pct None, risk_flag set, exit_reason data_missing."""
    pos = _pos()
    ep = _exit_plan()
    ev = evaluate_position(pos, 500.0, None, None, ep, date.today())
    assert ev["premium_capture_pct"] is None
    assert "MISSING_OPTION_QUOTE" in ev["risk_flags"]
    assert ev["exit_reason"] == "data_missing"
    assert ev["exit_signal"] == EXIT_HOLD


def test_bad_entry_premium_data_missing():
    """entry_premium <= 0 -> premium_capture_pct None, BAD_ENTRY_PREMIUM, data_missing."""
    pos = _pos(entry_premium=0)
    ep = _exit_plan()
    ev = evaluate_position(pos, 500.0, 1.0, 2.0, ep, date.today())
    assert ev["premium_capture_pct"] is None
    assert "BAD_ENTRY_PREMIUM" in ev["risk_flags"]
    assert ev["exit_reason"] == "data_missing"


def test_quote_resolver_finds_correct_bid_ask():
    """find_contract_quote returns bid/ask for matching exp, strike, option_type."""
    from app.core.positions.quote_resolver import find_contract_quote
    chain_rows = [
        {"exp": "2026-04-18", "strike": 500, "bid": 2.5, "ask": 2.6, "putCall": "P"},
        {"exp": "2026-04-18", "strike": 510, "bid": 3.0, "ask": 3.1, "putCall": "P"},
    ]
    q = find_contract_quote(chain_rows, "2026-04-18", 500, "PUT")
    assert q is not None
    assert q["bid"] == 2.5
    assert q["ask"] == 2.6
    # Strike as float
    q2 = find_contract_quote(chain_rows, "2026-04-18", 500.0, "PUT")
    assert q2 is not None
    assert q2["bid"] == 2.5
    # No match
    assert find_contract_quote(chain_rows, "2026-04-18", 520, "PUT") is None
    assert find_contract_quote(chain_rows, "2026-05-18", 500, "PUT") is None


def test_ledger_backward_compat_no_option_type(tmp_path: Path):
    """Old ledger without option_type: add_position_from_dict infers PUT for CSP, CALL for CC."""
    from app.core.positions.position_ledger import add_position_from_dict, load_open_positions
    ledger = tmp_path / "open_positions.json"
    # Dict without option_type, mode CSP -> should get option_type PUT
    add_position_from_dict({
        "symbol": "SPY",
        "mode": "CSP",
        "entry_date": "2026-01-01",
        "expiration": "2026-03-20",
        "strike": 500,
        "contracts": 1,
        "entry_premium": 10.0,
        "entry_spot": 498.0,
    }, ledger)
    open_list = load_open_positions(ledger)
    assert len(open_list) == 1
    assert open_list[0].get("option_type") == "PUT"
    # CC without option_type -> CALL
    add_position_from_dict({
        "symbol": "QQQ",
        "mode": "CC",
        "entry_date": "2026-01-01",
        "expiration": "2026-03-20",
        "strike": 400,
        "contracts": 1,
        "entry_premium": 5.0,
        "entry_spot": 398.0,
    }, ledger)
    open_list2 = load_open_positions(ledger)
    assert len(open_list2) == 2
    cc_pos = next(p for p in open_list2 if p["symbol"] == "QQQ")
    assert cc_pos.get("option_type") == "CALL"
