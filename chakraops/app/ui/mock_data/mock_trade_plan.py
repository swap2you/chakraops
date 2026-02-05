# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Mock TradePlanView for UI_MODE=MOCK (Phase 6.6)."""

from datetime import date

from app.ui_contracts.view_models import TradePlanView


def mock_trade_plan_blocked(decision_ts: str = "") -> TradePlanView:
    """BLOCKED trade proposal."""
    if not decision_ts:
        decision_ts = "2026-02-01T14:00:00Z"
    return TradePlanView(
        decision_ts=decision_ts,
        symbol="SPY",
        strategy_type="CSP",
        proposal={
            "symbol": "SPY",
            "strategy_type": "CSP",
            "expiry": date.today().isoformat(),
            "strikes": [450.0],
            "contracts": 1,
            "credit_estimate": 250.0,
            "max_loss": 500.0,
            "execution_status": "BLOCKED",
            "rejected": True,
            "rejection_reason": "Earnings window",
        },
        execution_status="BLOCKED",
        user_acknowledged=False,
        execution_notes="",
        exit_plan={"profit_target_pct": 0.6, "max_loss_multiplier": 2.0, "time_stop_days": 14},
        computed_targets={"t1": 100.0, "t2": 75.0, "t3": 37.5},
        blockers=["EARNINGS_WINDOW"],
    )


def mock_trade_plan_ready(decision_ts: str = "") -> TradePlanView:
    """READY trade proposal."""
    if not decision_ts:
        decision_ts = "2026-02-01T14:00:00Z"
    return TradePlanView(
        decision_ts=decision_ts,
        symbol="SPY",
        strategy_type="CSP",
        proposal={
            "symbol": "SPY",
            "strategy_type": "CSP",
            "expiry": "2026-04-18",
            "strikes": [450.0],
            "contracts": 1,
            "credit_estimate": 260.0,
            "max_loss": 520.0,
            "execution_status": "READY",
            "rejected": False,
        },
        execution_status="READY",
        user_acknowledged=False,
        execution_notes="",
        exit_plan={"profit_target_pct": 0.6, "max_loss_multiplier": 2.0, "time_stop_days": 14},
        computed_targets={"t1": 104.0, "t2": 78.0, "t3": 39.0},
        blockers=[],
    )
