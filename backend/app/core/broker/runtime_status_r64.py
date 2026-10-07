# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R64 production broker auth status + stale sizing gate."""

from __future__ import annotations

from typing import Any, Dict, Optional


def classify_broker_runtime_status(
    *,
    token_present: bool,
    snapshot: Optional[Dict[str, Any]] = None,
    sync_error: Optional[str] = None,
) -> Dict[str, Any]:
    """Map runtime conditions to UNAUTHENTICATED|AUTH_REQUIRED|READ_ONLY_AVAILABLE|STALE|ERROR."""
    if sync_error:
        return {
            "status": "ERROR",
            "manual_only": True,
            "trade_execution": False,
            "broker_writes": False,
            "sizing_blocked": True,
            "reason": sync_error,
        }
    if not token_present:
        return {
            "status": "UNAUTHENTICATED",
            "status_detail": "AUTH_REQUIRED",
            "manual_only": True,
            "trade_execution": False,
            "broker_writes": False,
            "sizing_blocked": True,
            "reason": "Robinhood production MCP token missing (Cursor MCP ≠ production).",
            "blocker": "ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER",
        }
    if snapshot and snapshot.get("stale"):
        return {
            "status": "STALE",
            "manual_only": True,
            "trade_execution": False,
            "broker_writes": False,
            "sizing_blocked": True,
            "reason": "Last-good broker snapshot is stale; new CSP sizing blocked.",
        }
    return {
        "status": "READ_ONLY_AVAILABLE",
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "sizing_blocked": False,
        "reason": "Read-only MCP token present; trade execution remains disabled.",
    }


def sizing_allowed_for_broker(status: Dict[str, Any]) -> bool:
    return not bool(status.get("sizing_blocked", True))
