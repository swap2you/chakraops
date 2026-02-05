# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""UI data contracts and read-model views (Phase 6.5).

Stable, denormalized view models for dashboard/UI consumption.
No trading logic; read-only queries and serialization.
"""

from app.ui_contracts.view_models import (
    AlertsView,
    DailyOverviewView,
    PerformanceSummaryView,
    PositionTimelineView,
    PositionView,
    TradePlanView,
)
from app.ui_contracts.view_builders import (
    build_alerts_view,
    build_daily_overview_view,
    build_performance_summary_view,
    build_position_timeline_view,
    build_position_view,
    build_trade_plan_view,
)

__all__ = [
    "PositionView",
    "PositionTimelineView",
    "TradePlanView",
    "DailyOverviewView",
    "PerformanceSummaryView",
    "AlertsView",
    "build_position_view",
    "build_position_timeline_view",
    "build_trade_plan_view",
    "build_daily_overview_view",
    "build_performance_summary_view",
    "build_alerts_view",
]
