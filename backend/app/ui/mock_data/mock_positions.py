# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Mock PositionView list for UI_MODE=MOCK (Phase 6.6). Phase 6.7: 6+ positions, notes, timeline events."""

from typing import Any, Dict, List

from app.ui_contracts.view_models import PositionView

# Phase 6.7: mock events per position_id for timeline in Positions tab
MOCK_POSITION_EVENTS: Dict[str, List[Dict[str, Any]]] = {
    "mock-pos-open": [
        {"event_type": "OPENED", "event_time": "2026-01-10T15:30:00Z", "metadata": {"source": "manual"}},
    ],
    "mock-pos-target-hit": [
        {"event_type": "OPENED", "event_time": "2026-01-20T14:00:00Z", "metadata": {}},
        {"event_type": "TARGET_1_HIT", "event_time": "2026-02-01T11:00:00Z", "metadata": {"notes": "Consider closing"}},
    ],
    "mock-pos-stop": [
        {"event_type": "OPENED", "event_time": "2026-01-05T10:00:00Z", "metadata": {}},
        {"event_type": "STOP_TRIGGERED", "event_time": "2026-02-01T09:00:00Z", "metadata": {"reason": "max_loss"}},
    ],
    "mock-pos-partial": [
        {"event_type": "OPENED", "event_time": "2025-12-01T12:00:00Z", "metadata": {}},
        {"event_type": "TARGET_1_HIT", "event_time": "2025-12-20T10:00:00Z", "metadata": {}},
        {"event_type": "MANUAL_NOTE", "event_time": "2025-12-21T09:00:00Z", "metadata": {"notes": "1 contract closed"}},
    ],
    "mock-pos-closed": [
        {"event_type": "OPENED", "event_time": "2025-11-15T14:00:00Z", "metadata": {}},
        {"event_type": "TARGET_1_HIT", "event_time": "2026-01-10T11:00:00Z", "metadata": {}},
        {"event_type": "CLOSED", "event_time": "2026-01-10T11:30:00Z", "metadata": {"realized_pnl": 95.0, "notes": "Closed at target"}},
    ],
    "mock-pos-assigned": [
        {"event_type": "OPENED", "event_time": "2025-10-01T13:00:00Z", "metadata": {}},
        {"event_type": "ASSIGNED", "event_time": "2025-12-20T16:00:00Z", "metadata": {"notes": "Assigned"}},
    ],
    "mock-pos-open-1": [
        {"event_type": "OPENED", "event_time": "2026-01-15T12:00:00Z", "metadata": {}},
    ],
}


def get_mock_position_events(position_id: str) -> List[Dict[str, Any]]:
    """Return mock events for a position (Phase 6.7). Empty list if unknown."""
    return list(MOCK_POSITION_EVENTS.get(position_id, []))


def mock_positions_empty() -> List[PositionView]:
    """No open positions."""
    return []


def mock_positions_open() -> List[PositionView]:
    """One open CSP position."""
    return [
        PositionView(
            position_id="mock-pos-open-1",
            symbol="SPY",
            strategy_type="CSP",
            lifecycle_state="OPEN",
            opened="2026-01-15",
            expiry="2026-03-21",
            strike=450.0,
            contracts=1,
            entry_credit=250.0,
            last_mark=None,
            dte=45,
            unrealized_pnl=None,
            realized_pnl=0.0,
            max_loss_estimate=500.0,
            profit_targets={"t1": 100.0, "t2": 75.0, "t3": 37.5},
            notes="",
            needs_attention=False,
            attention_reasons=[],
        ),
    ]


def mock_positions_mixed() -> List[PositionView]:
    """Mix: open, profit target hit, stop triggered, partially closed, closed with PnL, assigned."""
    return [
        PositionView(
            position_id="mock-pos-open",
            symbol="SPY",
            strategy_type="CSP",
            lifecycle_state="OPEN",
            opened="2026-01-10",
            expiry="2026-04-18",
            strike=440.0,
            contracts=1,
            entry_credit=200.0,
            last_mark=None,
            dte=60,
            unrealized_pnl=None,
            realized_pnl=0.0,
            max_loss_estimate=400.0,
            profit_targets={"t1": 80.0, "t2": 60.0, "t3": 30.0},
            notes="",
            needs_attention=False,
            attention_reasons=[],
        ),
        PositionView(
            position_id="mock-pos-target-hit",
            symbol="QQQ",
            strategy_type="CSP",
            lifecycle_state="OPEN",
            opened="2026-01-20",
            expiry="2026-03-20",
            strike=380.0,
            contracts=1,
            entry_credit=180.0,
            last_mark=72.0,
            dte=25,
            unrealized_pnl=None,
            realized_pnl=0.0,
            max_loss_estimate=360.0,
            profit_targets={"t1": 72.0, "t2": 54.0, "t3": 27.0},
            notes="",
            needs_attention=True,
            attention_reasons=["TARGET_1_HIT"],
        ),
        PositionView(
            position_id="mock-pos-stop",
            symbol="AAPL",
            strategy_type="CSP",
            lifecycle_state="OPEN",
            opened="2026-01-05",
            expiry="2026-02-20",
            strike=185.0,
            contracts=1,
            entry_credit=150.0,
            last_mark=320.0,
            dte=5,
            unrealized_pnl=None,
            realized_pnl=0.0,
            max_loss_estimate=300.0,
            profit_targets={"t1": 60.0, "t2": 45.0, "t3": 22.5},
            notes="",
            needs_attention=True,
            attention_reasons=["STOP_TRIGGERED"],
        ),
        PositionView(
            position_id="mock-pos-partial",
            symbol="META",
            strategy_type="CSP",
            lifecycle_state="PARTIALLY_CLOSED",
            opened="2025-12-01",
            expiry="2026-02-21",
            strike=350.0,
            contracts=2,
            entry_credit=400.0,
            last_mark=None,
            dte=30,
            unrealized_pnl=None,
            realized_pnl=80.0,
            max_loss_estimate=800.0,
            profit_targets={"t1": 160.0, "t2": 120.0, "t3": 60.0},
            notes="1 contract closed",
            needs_attention=False,
            attention_reasons=[],
        ),
        PositionView(
            position_id="mock-pos-closed",
            symbol="NVDA",
            strategy_type="CSP",
            lifecycle_state="CLOSED",
            opened="2025-11-15",
            expiry="2026-01-17",
            strike=120.0,
            contracts=1,
            entry_credit=220.0,
            last_mark=None,
            dte=None,
            unrealized_pnl=None,
            realized_pnl=95.0,
            max_loss_estimate=440.0,
            profit_targets={"t1": 88.0, "t2": 66.0, "t3": 33.0},
            notes="Closed at target",
            needs_attention=False,
            attention_reasons=[],
        ),
        PositionView(
            position_id="mock-pos-assigned",
            symbol="AMD",
            strategy_type="CSP",
            lifecycle_state="ASSIGNED",
            opened="2025-10-01",
            expiry="2025-12-20",
            strike=90.0,
            contracts=1,
            entry_credit=120.0,
            last_mark=None,
            dte=None,
            unrealized_pnl=None,
            realized_pnl=0.0,
            max_loss_estimate=240.0,
            profit_targets={"t1": 48.0, "t2": 36.0, "t3": 18.0},
            notes="Assigned",
            needs_attention=False,
            attention_reasons=[],
        ),
    ]
