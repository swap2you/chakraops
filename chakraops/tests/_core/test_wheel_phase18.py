# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 18.0: Wheel state machine and next action tests. Phase 19.0: Wheel policy tests."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.wheel.state_machine import update_state_from_position_event
from app.core.wheel.next_action import compute_next_action
from app.core.wheel.policy import evaluate_wheel_policy


@pytest.fixture
def tmp_wheel_state(tmp_path):
    path = tmp_path / "wheel_state.json"
    path.write_text(json.dumps({"symbols": {}}), encoding="utf-8")
    def _path():
        return path
    with patch("app.core.wheel.state_store._wheel_state_path", side_effect=_path):
        yield tmp_path


def test_wheel_state_transitions_open_close(tmp_wheel_state):
    sym = "SPY"
    pos_id = "pos-001"
    assert update_state_from_position_event(sym, "OPEN", pos_id) == "OPEN"
    from app.core.wheel.state_store import load_state
    data = load_state()
    entry = data["symbols"].get(sym)
    assert entry["state"] == "OPEN"
    assert pos_id in (entry.get("linked_position_ids") or [])
    assert update_state_from_position_event(sym, "CLOSE", pos_id) == "CLOSED"
    data2 = load_state()
    entry2 = data2["symbols"].get(sym)
    assert entry2["state"] == "CLOSED"
    assert pos_id not in (entry2.get("linked_position_ids") or [])


def test_next_action_blocked_when_risk_fail():
    result = compute_next_action(
        "SPY",
        {"state": "EMPTY", "last_updated_utc": None, "linked_position_ids": []},
        None,
        {"status": "FAIL", "breaches": []},
    )
    assert result["action_type"] == "BLOCKED"
    assert "portfolio_risk_FAIL" in (result.get("blocked_by") or [])


def test_next_action_open_ticket_when_empty_and_candidate():
    mock_artifact = type("Artifact", (), {})()
    mock_artifact.candidates_by_symbol = {
        "SPY": [type("C", (), {"contract_key": "100-2026-12-20-PUT", "strategy": "CSP"})()],
    }
    result = compute_next_action(
        "SPY",
        {"state": "EMPTY", "last_updated_utc": None, "linked_position_ids": []},
        mock_artifact,
        {"status": "PASS"},
    )
    assert result["action_type"] == "OPEN_TICKET"
    assert result["suggested_contract_key"] == "100-2026-12-20-PUT"


# Phase 19.0: Wheel policy
def test_policy_one_position_per_symbol_blocks_second():
    """When wheel_one_position_per_symbol is True and symbol already has open position, policy blocks."""
    account = type("Account", (), {"wheel_one_position_per_symbol": True, "wheel_min_dte": 21, "wheel_max_dte": 60, "wheel_min_iv_rank": None})()
    open_pos = [type("P", (), {"symbol": "SPY", "status": "OPEN", "position_id": "p1"})()]
    result = evaluate_wheel_policy(account, "SPY", {"state": "EMPTY"}, None, open_pos, expiration="2026-12-20")
    assert result["allowed"] is False
    assert "wheel_one_position_per_symbol" in (result.get("blocked_by") or [])


def test_next_action_blocked_when_policy_violated():
    """next_action returns BLOCKED when wheel policy blocks (e.g. one_per_symbol and already open)."""
    account = type("Account", (), {"wheel_one_position_per_symbol": True, "wheel_min_dte": 21, "wheel_max_dte": 60, "wheel_min_iv_rank": None})()
    open_pos = [type("P", (), {"symbol": "SPY", "status": "OPEN", "position_id": "p1"})()]
    result = compute_next_action(
        "SPY",
        {"state": "EMPTY", "last_updated_utc": None, "linked_position_ids": []},
        type("Artifact", (), {"candidates_by_symbol": {"SPY": [type("C", (), {"contract_key": "100-2026-12-20-PUT", "expiry": "2026-12-20"})()]}})(),
        {"status": "PASS"},
        account=account,
        open_positions=open_pos,
    )
    assert result["action_type"] == "BLOCKED"
    assert any("wheel_one_position_per_symbol" in b for b in (result.get("blocked_by") or []))


def test_add_paper_position_409_when_wheel_policy_blocks(tmp_path):
    """Cannot open second CSP for same symbol when wheel_one_position_per_symbol enabled."""
    from app.core.positions.service import add_paper_position
    from app.core.accounts.models import Account

    out = tmp_path / "out"
    out.mkdir(parents=True)
    (out / "accounts").mkdir(parents=True, exist_ok=True)
    (out / "positions").mkdir(parents=True, exist_ok=True)
    (out / "accounts").mkdir(parents=True, exist_ok=True)
    acc_path = out / "accounts" / "accounts.json"
    acc_path.write_text(json.dumps([{
        "account_id": "paper",
        "provider": "Manual",
        "account_type": "Taxable",
        "total_capital": 100000,
        "max_capital_per_trade_pct": 5,
        "max_total_exposure_pct": 30,
        "allowed_strategies": ["CSP"],
        "is_default": True,
        "active": True,
        "wheel_one_position_per_symbol": True,
        "wheel_min_dte": 21,
        "wheel_max_dte": 60,
    }]), encoding="utf-8")
    # One existing open position for SPY (paper account)
    pos_path = out / "positions" / "positions.json"
    pos_path.write_text(json.dumps([{
        "position_id": "pos-existing",
        "account_id": "paper",
        "symbol": "SPY",
        "strategy": "CSP",
        "contracts": 1,
        "strike": 100,
        "expiration": "2026-12-20",
        "status": "OPEN",
        "opened_at": "2026-01-01T00:00:00Z",
        "underlying": "SPY",
        "option_type": "PUT",
        "contract_key": "100-2026-12-20-PUT",
    }]), encoding="utf-8")
    wheel_path = out / "wheel_state.json"
    wheel_path.write_text(json.dumps({"symbols": {"SPY": {"state": "OPEN", "linked_position_ids": ["pos-existing"]}}}), encoding="utf-8")

    with patch("app.core.settings.get_output_dir", return_value=str(out)):
        with patch("app.core.wheel.state_store._wheel_state_path", return_value=wheel_path):
            payload = {
                "symbol": "SPY",
                "strategy": "CSP",
                "contracts": 1,
                "strike": 100,
                "expiration": "2026-12-20",
                "contract_key": "100-2026-12-20-PUT",
                "open_credit": 1.5,
            }
            pos2, err2, code2 = add_paper_position(payload)
            assert pos2 is None and code2 == 409, (pos2, err2, code2)
            assert any("Wheel policy" in (e or "") for e in err2)
