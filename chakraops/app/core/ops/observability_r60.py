# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R60 connected-system observability status (operational recovery only)."""

from __future__ import annotations

from typing import Any, Dict

from app.core.broker.status import robinhood_mcp_read_only_status
from app.core.monitor.advisory_worker_r54 import monitor_status


def connected_observability_status() -> Dict[str, Any]:
    broker = robinhood_mcp_read_only_status()
    monitor = monitor_status()
    components = {
        "api": {"status": "OK"},
        "broker_mcp": {
            "status": broker.get("status"),
            "blocker": broker.get("blocker"),
            "read_only_available": broker.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE"),
        },
        "advisory_monitor": {
            "status": "RUNNING" if monitor.get("running") else "IDLE",
            "last_run_at": monitor.get("last_run_at"),
            "signal_count": monitor.get("signal_count"),
        },
        "legacy_scheduler": {"status": "DISABLED", "enabled": False},
    }
    degraded = []
    if not broker.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE"):
        degraded.append("broker_mcp_unauthenticated")
    return {
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "auto_rule_mutation": False,
        "components": components,
        "degraded": degraded,
        "recovery_policy": "reconnect/retry/worker-restart/cache-refresh only — never auto orders",
    }
