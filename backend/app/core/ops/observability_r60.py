# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R60 connected-system observability status (operational recovery only)."""

from __future__ import annotations

import os
from typing import Any, Dict

from app.core.broker.status import robinhood_mcp_read_only_status
from app.core.monitor.advisory_worker_r54 import monitor_status


def _orats_component() -> Dict[str, Any]:
    """R70-DEF-052: real/env probe or explicit stub — never hardcode healthy."""
    flag = os.environ.get("R65_ORATS_OK")
    if flag is not None:
        ok = flag.strip().lower() in {"1", "true", "yes"}
        return {
            "status": "OK" if ok else "DEGRADED",
            "probe": "env:R65_ORATS_OK",
            "stub": False,
        }
    try:
        from app.core.config.orats_secrets import get_orats_token

        if not get_orats_token():
            return {
                "status": "UNAVAILABLE",
                "probe": "token_absent",
                "stub": False,
            }
    except Exception:
        pass
    return {
        "status": "UNAVAILABLE",
        "probe": "not_probed",
        "stub": True,
        "note": "ORATS live probe not run in this observability path",
    }


def connected_observability_status() -> Dict[str, Any]:
    broker = robinhood_mcp_read_only_status()
    monitor = monitor_status()
    orats = _orats_component()
    components = {
        "api": {"status": "OK", "probe": "process_alive"},
        "broker_mcp": {
            "status": broker.get("status"),
            "blocker": broker.get("blocker"),
            "read_only_available": broker.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE"),
        },
        "orats": orats,
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
    if (orats.get("status") or "").upper() not in {"OK", "UP"}:
        degraded.append("orats_degraded")
    return {
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "auto_rule_mutation": False,
        "components": components,
        "degraded": degraded,
        "recovery_policy": "reconnect/retry/worker-restart/cache-refresh only — never auto orders",
    }
