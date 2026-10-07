# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.1: Position-aware next_action_code (ENTRY/HOLD/CLOSE/ROLL/NONE) — request-time only."""

import pytest

from app.core.next_action_r241 import (
    compute_next_action_options,
    compute_next_action_shares,
    build_next_action_details,
)


def test_options_entry_when_no_position_and_selected_contract():
    code, rationale, key = compute_next_action_options(
        has_open_option=False,
        selected_contract_key="SPY_20260320_C_450",
        exit_plan={"stop": 440, "t1": 460},
        spot=455.0,
        delta_best=0.30,
        dte=35,
    )
    assert code == "ENTRY"
    assert any("entry" in r.lower() for r in rationale)
    assert key.get("spot") == 455.0
    assert key.get("delta_best") == 0.30


def test_options_close_when_stop_hit():
    code, rationale, _ = compute_next_action_options(
        has_open_option=True,
        selected_contract_key="X",
        exit_plan={"stop": 100.0, "t1": 110.0},
        spot=99.0,
    )
    assert code == "CLOSE"
    assert any("stop" in r.lower() for r in rationale)


def test_options_close_when_target_hit():
    code, rationale, _ = compute_next_action_options(
        has_open_option=True,
        selected_contract_key="X",
        exit_plan={"stop": 100.0, "t1": 110.0, "targets_already_exceeded": True},
        spot=105.0,
    )
    assert code == "CLOSE"
    assert any("target" in r.lower() for r in rationale)


def test_options_roll_when_low_dte():
    code, rationale, _ = compute_next_action_options(
        has_open_option=True,
        selected_contract_key="X",
        exit_plan={"stop": 100.0, "t1": 110.0},
        spot=105.0,
        dte=8,
    )
    assert code == "ROLL"
    assert any("dte" in r.lower() or "roll" in r.lower() for r in rationale)


def test_options_hold_when_position_open_and_no_exit():
    code, _, _ = compute_next_action_options(
        has_open_option=True,
        selected_contract_key="X",
        exit_plan={"stop": 100.0, "t1": 110.0},
        spot=105.0,
        dte=30,
    )
    assert code == "HOLD"


def test_shares_entry_when_eligible_no_position():
    code, rationale, _ = compute_next_action_shares(
        shares_eligible=True,
        has_shares_position=False,
        spot=50.0,
    )
    assert code == "ENTRY"
    assert any("entry" in r.lower() for r in rationale)


def test_shares_hold_when_position_open():
    code, _, _ = compute_next_action_shares(
        shares_eligible=True,
        has_shares_position=True,
        shares_plan={"eligible": True},
        exit_plan_or_targets={"t1": 55.0, "stop": 45.0},
        spot=50.0,
    )
    assert code == "HOLD"


def test_shares_close_when_stop_hit():
    code, rationale, _ = compute_next_action_shares(
        shares_eligible=True,
        has_shares_position=True,
        exit_plan_or_targets={"t1": 55.0, "stop": 45.0},
        spot=44.0,
    )
    assert code == "CLOSE"
    assert any("stop" in r.lower() for r in rationale)


def test_build_next_action_details_safe_output():
    details = build_next_action_details(
        "OPTIONS", "ENTRY", ["Eligible for entry."], {"spot": 100.0, "delta_best": 0.28},
        contract_key="SPY_20260320_C_450", premium_est=250.0,
    )
    assert details["action"] == "ENTRY"
    assert details["rationale_lines"] == ["Eligible for entry."]
    assert "FAIL_" not in str(details)
    assert "WARN_" not in str(details)
    assert details.get("key_numbers", {}).get("spot") == 100.0
    assert details.get("contract_key") == "SPY_20260320_C_450"
