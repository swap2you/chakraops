# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Mock AlertsView for UI_MODE=MOCK (Phase 6.6)."""

from datetime import datetime, timezone

from app.ui_contracts.view_models import AlertsView


def mock_alerts_empty(as_of: str = "") -> AlertsView:
    """No alerts."""
    if not as_of:
        as_of = datetime.now(timezone.utc).isoformat()
    return AlertsView(as_of=as_of, items=[])


def mock_alerts_profit_target(as_of: str = "") -> AlertsView:
    """Profit target hit alert."""
    if not as_of:
        as_of = datetime.now(timezone.utc).isoformat()
    return AlertsView(
        as_of=as_of,
        items=[
            {
                "level": "info",
                "code": "PROFIT_TARGET_HIT",
                "message": "Profit target hit",
                "symbol": "QQQ",
                "position_id": "mock-pos-target-hit",
                "decision_ts": None,
            },
        ],
    )


def mock_alerts_stop_triggered(as_of: str = "") -> AlertsView:
    """Stop triggered alert."""
    if not as_of:
        as_of = datetime.now(timezone.utc).isoformat()
    return AlertsView(
        as_of=as_of,
        items=[
            {
                "level": "warning",
                "code": "STOP_TRIGGERED",
                "message": "Stop triggered",
                "symbol": "AAPL",
                "position_id": "mock-pos-stop",
                "decision_ts": None,
            },
        ],
    )


def mock_alerts_freeze_violation(as_of: str = "") -> AlertsView:
    """Freeze violation alert."""
    if not as_of:
        as_of = datetime.now(timezone.utc).isoformat()
    return AlertsView(
        as_of=as_of,
        items=[
            {
                "level": "error",
                "code": "FREEZE_VIOLATION",
                "message": "Config changed: volatility.vol_target, scoring.min_score",
                "symbol": "",
                "position_id": None,
                "decision_ts": None,
            },
        ],
    )


def mock_alerts_no_trade(as_of: str = "") -> AlertsView:
    """NO TRADE informational alert."""
    if not as_of:
        as_of = datetime.now(timezone.utc).isoformat()
    return AlertsView(
        as_of=as_of,
        items=[
            {
                "level": "info",
                "code": "NO_TRADE",
                "message": "No trade; top blocker: REGIME",
                "symbol": "",
                "position_id": None,
                "decision_ts": None,
            },
        ],
    )
