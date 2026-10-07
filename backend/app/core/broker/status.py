# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52/R64/R70 Robinhood MCP read-only status helpers for UI/API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.broker.allowlist import (
    ROBINHOOD_READ_TOOL_ALLOWLIST,
    ROBINHOOD_WRITE_TOOL_DENYLIST,
)
from app.core.broker.robinhood_mcp_client import (
    BLOCKER_RUNTIME_AUTH,
    STATUS_AUTH_REQUIRED,
    STATUS_UNAUTHENTICATED,
    auth_status,
    resolve_access_token,
)
from app.core.broker.robinhood_oauth import oauth_status

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

    R64/R70 statuses: UNAUTHENTICATED / AUTH_REQUIRED / READ_ONLY_AVAILABLE / STALE / ERROR.
    Always manual_only=true, trade_execution=false. Never exposes write capability.
    """
    auth = auth_status()
    oauth = oauth_status()
    token_present = bool(resolve_access_token(refresh_if_expired=False)) and not oauth.get("needs_reauth")
    blocker: Optional[str] = None

    # AUTH_REQUIRED when OAuth store needs browser re-auth, or caller signals 401 path.
    needs_auth = bool(
        auth_required
        or auth.get("auth_required")
        or oauth.get("auth_required")
        or oauth.get("needs_reauth")
    )

    if last_error:
        status = STATUS_ERROR
        code = "ROBINHOOD_MCP_ERROR"
        reason = f"Robinhood MCP read path error: {last_error}"
        blocker = code
    elif not token_present:
        # AUTH_REQUIRED when operator must complete OAuth; UNAUTHENTICATED when simply missing.
        status = STATUS_AUTH_REQUIRED if needs_auth else STATUS_UNAUTHENTICATED
        code = BLOCKER_RUNTIME_AUTH
        if status == STATUS_AUTH_REQUIRED:
            reason = (
                "Robinhood MCP OAuth authorization required. "
                "Run scripts/robinhood_mcp_authorize.ps1 to complete ChakraOps browser OAuth "
                "(Cursor MCP session ≠ ChakraOps app auth). App remains up; manual portfolio path still valid."
            )
        else:
            reason = (
                "Robinhood MCP access token not configured "
                "(complete ChakraOps OAuth via scripts/robinhood_mcp_authorize.ps1, "
                "or set ROBINHOOD_MCP_ACCESS_TOKEN / ROBINHOOD_MCP_TOKEN_PATH for migration). "
                "Cursor MCP session ≠ ChakraOps app auth. App remains up; manual portfolio path still valid."
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
        "oauth": oauth,
        # Capability flag: usable token configured (may still be STALE/ERROR).
        "ROBINHOOD_MCP_READ_ONLY_AVAILABLE": token_present,
        "snapshot_stale": snapshot_stale,
    }
