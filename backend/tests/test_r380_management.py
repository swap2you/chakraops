# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 — open option management CLOSE/ROLL/HOLD."""

from datetime import date, timedelta

from app.core.decision_engine.wheel_v2.management import manage_open_option


def _pos(**kw):
    defaults = {
        "strategy": "CSP",
        "strike": 100.0,
        "expiration": (date.today() + timedelta(days=30)).isoformat(),
        "open_credit": 2.0,
        "contracts": 1,
    }
    defaults.update(kw)
    return type("P", (), defaults)()


def test_management_hold_far_from_targets():
    pos = _pos()
    out = manage_open_option(
        pos,
        {"profit_management": {"take_profit_pct": 50.0, "roll_at_dte": 14}},
        mark_proxy=1.5,
    )
    assert out["action"] == "HOLD"
    assert out["manual_only"] is True
    assert out["trade_execution"] is False


def test_management_close_on_take_profit():
    pos = _pos()
    # credit 2.0, mark 0.5 → 75% profit ≥ 50% target
    out = manage_open_option(
        pos,
        {"profit_management": {"take_profit_pct": 50.0, "roll_at_dte": 14}},
        mark_proxy=0.5,
    )
    assert out["action"] == "CLOSE"
    assert out["pct_max_profit"] is not None and out["pct_max_profit"] >= 50.0


def test_management_roll_in_dte_window():
    pos = _pos(expiration=(date.today() + timedelta(days=10)).isoformat())
    out = manage_open_option(
        pos,
        {"profit_management": {"take_profit_pct": 80.0, "roll_at_dte": 14}},
        mark_proxy=1.8,
    )
    assert out["action"] == "ROLL"
    assert out["roll_at_dte"] == 14


def test_management_uses_profile_defaults_when_empty():
    pos = _pos()
    out = manage_open_option(pos, None, mark_proxy=1.5)
    assert out["action"] in ("CLOSE", "ROLL", "HOLD")
    assert out["profit_target_pct"] == 50.0
