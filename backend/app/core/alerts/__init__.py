# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6: Alert engine — stage-aware, deduplicated, actionable alerts.
Slack is a delivery channel only; alert logic lives here.
"""

from app.core.alerts.alert_engine import (
    process_run_completed,
    list_recent_alert_records,
    get_alerting_status,
)
from app.core.alerts.models import (
    Alert,
    AlertType,
    Severity,
)

__all__ = [
    "Alert",
    "AlertType",
    "Severity",
    "process_run_completed",
    "list_recent_alert_records",
    "get_alerting_status",
]
