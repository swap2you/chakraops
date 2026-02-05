# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Mock DailyOverviewView for UI_MODE=MOCK (Phase 6.6)."""

from datetime import date

from app.ui_contracts.view_models import DailyOverviewView


def mock_daily_overview_no_trade(as_of_date: str = "") -> DailyOverviewView:
    """NO TRADE — capital protected."""
    if not as_of_date:
        as_of_date = date.today().isoformat()
    return DailyOverviewView(
        date=as_of_date,
        run_mode="DRY_RUN",
        config_frozen=True,
        freeze_violation_changed_keys=[],
        regime="NEUTRAL",
        regime_reason="VIX in range",
        symbols_evaluated=50,
        selected_signals=0,
        trades_ready=0,
        no_trade=True,
        why_summary="No READY trade; capital protected.",
        top_blockers=[{"code": "REGIME", "count": 1}, {"code": "MIN_SCORE", "count": 3}],
        risk_posture="CONSERVATIVE",
        links={},
    )


def mock_daily_overview_blocked(as_of_date: str = "") -> DailyOverviewView:
    """BLOCKED trade (gate blocked)."""
    if not as_of_date:
        as_of_date = date.today().isoformat()
    return DailyOverviewView(
        date=as_of_date,
        run_mode="PAPER_LIVE",
        config_frozen=True,
        freeze_violation_changed_keys=[],
        regime="NEUTRAL",
        regime_reason="",
        symbols_evaluated=48,
        selected_signals=1,
        trades_ready=0,
        no_trade=True,
        why_summary="Gate blocked: earnings window.",
        top_blockers=[{"code": "EARNINGS_WINDOW", "count": 1}],
        risk_posture="CONSERVATIVE",
        links={"latest_decision_ts": f"{as_of_date}T14:00:00Z"},
    )


def mock_daily_overview_one_ready(as_of_date: str = "") -> DailyOverviewView:
    """1 READY trade available."""
    if not as_of_date:
        as_of_date = date.today().isoformat()
    return DailyOverviewView(
        date=as_of_date,
        run_mode="PAPER_LIVE",
        config_frozen=True,
        freeze_violation_changed_keys=[],
        regime="NEUTRAL",
        regime_reason="",
        symbols_evaluated=52,
        selected_signals=1,
        trades_ready=1,
        no_trade=False,
        why_summary="1 safe trade available (SPY CSP).",
        top_blockers=[],
        risk_posture="CONSERVATIVE",
        links={"latest_decision_ts": f"{as_of_date}T14:00:00Z"},
    )


def mock_daily_overview_multi_ready(as_of_date: str = "") -> DailyOverviewView:
    """Multiple READY trades."""
    if not as_of_date:
        as_of_date = date.today().isoformat()
    return DailyOverviewView(
        date=as_of_date,
        run_mode="LIVE",
        config_frozen=True,
        freeze_violation_changed_keys=[],
        regime="NEUTRAL",
        regime_reason="",
        symbols_evaluated=55,
        selected_signals=3,
        trades_ready=3,
        no_trade=False,
        why_summary="3 safe trades available.",
        top_blockers=[],
        risk_posture="BALANCED",
        links={"latest_decision_ts": f"{as_of_date}T14:00:00Z"},
    )


def mock_daily_overview_freeze_violation(as_of_date: str = "") -> DailyOverviewView:
    """Freeze violation — config changed."""
    if not as_of_date:
        as_of_date = date.today().isoformat()
    return DailyOverviewView(
        date=as_of_date,
        run_mode="PAPER_LIVE",
        config_frozen=False,
        freeze_violation_changed_keys=["volatility.vol_target", "scoring.min_score"],
        regime=None,
        regime_reason=None,
        symbols_evaluated=0,
        selected_signals=0,
        trades_ready=0,
        no_trade=True,
        why_summary="Execution blocked: config changed since last run.",
        top_blockers=[],
        risk_posture="CONSERVATIVE",
        links={},
    )
