# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R37/R52 broker status + read-only snapshot API. No write/order endpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, Query

from app.core.broker.models import ACCOUNT_ALIASES, redact_account_fields
from app.core.broker.read_only_policy import robinhood_integration_status
from app.core.broker.snapshot_store import load_snapshot, persist_sync_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ui/broker", tags=["broker"])


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    """Reuse UI key gate when UI_API_KEY is set (local dev allows when unset)."""
    import os

    expected = (os.getenv("UI_API_KEY") or "").strip()
    if not expected:
        return
    from fastapi import HTTPException

    if (x_ui_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


@router.get("/status")
def broker_status(
    account_alias: str = Query("acct_individual", description="Account alias for stale check"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Return Robinhood MCP read-only status (never enables trade execution).

    R64 production statuses: UNAUTHENTICATED / AUTH_REQUIRED / READ_ONLY_AVAILABLE / STALE / ERROR.
    """
    _require_ui_key(x_ui_key)
    from app.core.broker.status import robinhood_mcp_read_only_status

    import os

    alias = (account_alias or "").strip() or "acct_individual"
    snap = load_snapshot(alias)
    token_path = (os.getenv("ROBINHOOD_MCP_TOKEN_PATH") or "").strip()
    token_env = (os.getenv("ROBINHOOD_MCP_ACCESS_TOKEN") or "").strip()
    token_configured = bool(token_env or token_path)
    stale: Optional[bool]
    if snap is not None:
        stale = bool(snap.stale)
    elif token_configured:
        stale = True
    else:
        stale = None
    return robinhood_mcp_read_only_status(
        snapshot_stale=stale,
        auth_required=bool(token_path) and not token_env,
    )

@router.get("/accounts")
def broker_accounts(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    """List broker accounts with masked account numbers / aliases only."""
    _require_ui_key(x_ui_key)
    status = robinhood_integration_status()
    accounts: list = []
    errors: list = []
    try:
        from app.core.broker.robinhood_mcp_provider import RobinhoodMcpReadProvider

        if status.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE"):
            provider = RobinhoodMcpReadProvider()
            accounts = [a.to_dict() for a in provider.list_accounts()]
        else:
            errors.append(status.get("blocker") or "UNAUTHENTICATED")
    except Exception as exc:
        logger.warning("broker accounts list failed: %s", type(exc).__name__)
        errors.append(type(exc).__name__)

    return {
        "manual_only": True,
        "trade_execution": False,
        "accounts": redact_account_fields(accounts),
        "known_aliases": list(ACCOUNT_ALIASES),
        "errors": errors,
        "status": status.get("status"),
    }


@router.get("/snapshot")
def broker_snapshot(
    account_alias: str = Query("acct_individual", description="Account alias (not full account number)"),
    refresh: bool = Query(False, description="If true, attempt live MCP sync when authenticated"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Return last-good (or freshly synced) snapshot; masked; fail-closed on errors."""
    _require_ui_key(x_ui_key)
    alias = (account_alias or "").strip() or "acct_individual"
    status = robinhood_integration_status()
    sync_meta: Dict[str, Any] = {"refreshed": False}

    if refresh and status.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE"):
        try:
            from app.core.broker.robinhood_mcp_provider import RobinhoodMcpReadProvider

            provider = RobinhoodMcpReadProvider()
            snap = provider.sync_snapshot(alias)
            sync_meta = persist_sync_result(alias, snap, failed=bool(snap.errors and snap.completeness == "empty"))
            sync_meta["refreshed"] = True
        except Exception as exc:
            logger.warning("broker snapshot refresh failed: %s", type(exc).__name__)
            sync_meta = persist_sync_result(alias, None, failed=True)
            sync_meta["error"] = type(exc).__name__

    stored = load_snapshot(alias)
    return {
        "manual_only": True,
        "trade_execution": False,
        "account_alias": alias,
        "snapshot": stored.masked_for_api() if stored else None,
        "stale": bool(stored.stale) if stored else True,
        "sync": sync_meta,
        "status": status.get("status"),
    }


@router.get("/reconcile")
def broker_reconcile_summary(
    account_alias: str = Query("acct_individual"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R53: compare manual holdings vs broker snapshot. No auto-mutation."""
    _require_ui_key(x_ui_key)
    from app.core.broker.reconcile_r53 import reconcile_manual_vs_broker

    snap = load_snapshot(account_alias)
    manual_holdings: list = []
    try:
        from app.core.portfolio import holdings_db  # type: ignore

        if hasattr(holdings_db, "list_holdings"):
            manual_holdings = list(holdings_db.list_holdings() or [])
        elif hasattr(holdings_db, "get_holdings"):
            manual_holdings = list(holdings_db.get_holdings() or [])
    except Exception:
        manual_holdings = []

    broker_equities = []
    if snap is not None:
        broker_equities = [p.to_dict() for p in snap.equity_positions]

    result = reconcile_manual_vs_broker(manual_holdings, broker_equities)
    result.update(
        {
            "account_alias": account_alias,
            "has_broker_snapshot": snap is not None,
            "snapshot_stale": bool(snap.stale) if snap else None,
            "actions": [],
        }
    )
    return result
