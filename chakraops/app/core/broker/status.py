# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52/R64 Robinhood MCP read-only status helpers for UI/API."""

from __future__ import annotations

from typing import Any, Dict, Optional

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

STATUS_AUTH_REQUIRED = "AUTH_REQUIRED"
STATUS_READ_ONLY_AVAILABLE = "READ_ONLY_AVAILABLE"
STATUS_STALE = "STALE"
STATUS_ERROR = "ERROR"
STATUS_CODE_READ_ONLY = "ROBINHOOD_MCP_READ_ONLY_AVAILABLE"

PRODUCTION_AUTH_STATUSES = frozenset(
    {
        STATUS_UNAUTHENTICATED,
        STATUS_AUTH_REQUIRED,
        STATUS_READ_ONLY_AVAILABLE,
        STATUS_STALE,
        STATUS_ERROR,
    }
)


def robinhood_mcp_read_only_status(
    *,
    snapshot_stale: Optional[bool] = None,
    last_error: Optional[str] = None,
    auth_required: bool = False,
) -> Dict[str, Any]:
    """Status payload for /api/ui/broker/status.

    R64 statuses: UNAUTHENTICATED / AUTH_REQUIRED / READ_ONLY_AVAILABLE / STALE / ERROR.
    Always manual_only=true, trade_execution=false. Never exposes write capability.
    """
    auth = auth_status()
    token_present = bool(resolve_access_token())
    blocker: Optional[str] = None

    if last_error:
        status = STATUS_ERROR
        code = "ROBINHOOD_MCP_ERROR"
        reason = f"Robinhood MCP read path error: {last_error}"
        blocker = code
    elif not token_present:
        # AUTH_REQUIRED when operator must complete OAuth; UNAUTHENTICATED when simply missing.
        status = STATUS_AUTH_REQUIRED if auth_required else STATUS_UNAUTHENTICATED
        code = BLOCKER_RUNTIME_AUTH
        reason = (
            "Robinhood MCP access token not configured "
            "(set ROBINHOOD_MCP_ACCESS_TOKEN or ROBINHOOD_MCP_TOKEN_PATH on the VPS). "
            "Cursor MCP session ≠ production auth. App remains up; manual portfolio path still valid."
        )
        blocker = BLOCKER_RUNTIME_AUTH
    elif snapshot_stale is True:
        status = STATUS_STALE
        code = "ROBINHOOD_MCP_STALE"
        reason = (
            "Token present but last-good broker snapshot is stale or untrusted. "
            "Prior snapshot remains visible; CSP sizing blocked until fresh sync."
        )
    else:
        status = STATUS_READ_ONLY_AVAILABLE
        code = STATUS_CODE_READ_ONLY
        reason = (
            "Robinhood MCP OAuth token configured. Read-only broker sync is available. "
            "Trade execution remains disabled; write tools are denied."
        )

    return {
        "status": status,
        "status_code": code,
        "reason": reason,
        "blocker": blocker,
        "production_auth_statuses": sorted(PRODUCTION_AUTH_STATUSES),
        "manual_portfolio": True,
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "broker": "robinhood",
        "integration": "robinhood_mcp",
        "mode": "read_only",
        "read_allowlist_enabled": True,
        "read_allowlist": sorted(ROBINHOOD_READ_TOOL_ALLOWLIST),
        "write_denylist": sorted(ROBINHOOD_WRITE_TOOL_DENYLIST),
        "auth": auth,
        # Capability flag: token configured (may still be STALE/ERROR).
        "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": token_present,
        "snapshot_stale": snapshot_stale,
    }
