# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Mock data for UI_MODE=MOCK (Phase 6.6). All mocks use view models from app.ui_contracts."""

from app.ui.mock_data.mock_artifact import get_mock_artifact
from app.ui.mock_data.mock_daily_overview import (
    mock_daily_overview_no_trade,
    mock_daily_overview_blocked,
    mock_daily_overview_one_ready,
    mock_daily_overview_multi_ready,
    mock_daily_overview_freeze_violation,
)
from app.ui.mock_data.mock_positions import (
    mock_positions_open,
    mock_positions_mixed,
    mock_positions_empty,
    get_mock_position_events,
)
from app.ui.mock_data.mock_alerts import (
    mock_alerts_empty,
    mock_alerts_profit_target,
    mock_alerts_stop_triggered,
    mock_alerts_freeze_violation,
    mock_alerts_no_trade,
)
from app.ui.mock_data.mock_trade_plan import (
    mock_trade_plan_blocked,
    mock_trade_plan_ready,
)

__all__ = [
    "get_mock_artifact",
    "mock_daily_overview_no_trade",
    "mock_daily_overview_blocked",
    "mock_daily_overview_one_ready",
    "mock_daily_overview_multi_ready",
    "mock_daily_overview_freeze_violation",
    "mock_positions_open",
    "mock_positions_mixed",
    "mock_positions_empty",
    "get_mock_position_events",
    "mock_alerts_empty",
    "mock_alerts_profit_target",
    "mock_alerts_stop_triggered",
    "mock_alerts_freeze_violation",
    "mock_alerts_no_trade",
    "mock_trade_plan_blocked",
    "mock_trade_plan_ready",
]
