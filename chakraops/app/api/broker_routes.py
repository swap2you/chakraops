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
def broker_status(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    """Return Robinhood MCP read-only status (never enables trade execution)."""
    _require_ui_key(x_ui_key)
    return robinhood_integration_status()


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
    """R52 stub: reconcile summary placeholder (no auto-mutation)."""
    _require_ui_key(x_ui_key)
    snap = load_snapshot(account_alias)
    return {
        "manual_only": True,
        "trade_execution": False,
        "account_alias": account_alias,
        "status": "STUB",
        "message": "R52 reconcile summary stub — comparison rules deferred; no auto-mutation.",
        "has_broker_snapshot": snap is not None,
        "snapshot_stale": bool(snap.stale) if snap else None,
        "diffs": [],
        "actions": [],
    }
