# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52 Robinhood MCP read-only status helpers for UI/API."""

from __future__ import annotations

from typing import Any, Dict

from app.core.broker.allowlist import (
    ROBINHOOD_READ_TOOL_ALLOWLIST,
    ROBINHOOD_WRITE_TOOL_DENYLIST,
)
from app.core.broker.robinhood_mcp_client import (
    BLOCKER_RUNTIME_AUTH,
    STATUS_UNAUTHENTICATED,
    auth_status,
    resolve_access_token,
)

STATUS_READ_ONLY_AVAILABLE = "READ_ONLY_AVAILABLE"
STATUS_CODE_READ_ONLY = "ROBINHOOD_MCP_READ_ONLY_AVAILABLE"


def robinhood_mcp_read_only_status() -> Dict[str, Any]:
    """Status payload for /api/ui/broker/status.

    When a token is configured → READ_ONLY_AVAILABLE (not permanent NO_GO).
    When missing → UNAUTHENTICATED with ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER.
    Always manual_only=true, trade_execution=false.
    """
    auth = auth_status()
    token_present = bool(resolve_access_token())

    if token_present:
        status = STATUS_READ_ONLY_AVAILABLE
        code = STATUS_CODE_READ_ONLY
        reason = (
            "Robinhood MCP OAuth token configured. Read-only broker sync is available. "
            "Trade execution remains disabled; write tools are denied."
        )
        blocker = None
    else:
        status = STATUS_UNAUTHENTICATED
        code = BLOCKER_RUNTIME_AUTH
        reason = (
            "Robinhood MCP access token not configured "
            "(set ROBINHOOD_MCP_ACCESS_TOKEN or ROBINHOOD_MCP_TOKEN_PATH). "
            "App remains up; manual portfolio path still valid."
        )
        blocker = BLOCKER_RUNTIME_AUTH

    return {
        "status": status,
        "status_code": code,
        "reason": reason,
        "blocker": blocker,
        "manual_portfolio": True,
        "manual_only": True,
        "trade_execution": False,
        "broker": "robinhood",
        "integration": "robinhood_mcp",
        "mode": "read_only",
        "read_allowlist_enabled": True,
        "read_allowlist": sorted(ROBINHOOD_READ_TOOL_ALLOWLIST),
        "write_denylist": sorted(ROBINHOOD_WRITE_TOOL_DENYLIST),
        "auth": auth,
        "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": token_present,
    }
