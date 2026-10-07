# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R66 multi-account risk + hedge advisory UI routes (no broker writes)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.core.broker.fake_provider import FakeBrokerReadProvider
from app.core.broker.models import BrokerSnapshot
from app.core.broker.provider import BrokerReadProvider
from app.core.portfolio.hedge_advisory_r66 import build_hedge_scenarios
from app.core.portfolio.multi_account_risk_r66 import evaluate_multi_account_risk

router = APIRouter(prefix="/api/ui/portfolio", tags=["portfolio-risk-r66"])


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    import os

    expected = (os.getenv("UI_API_KEY") or "").strip()
    if not expected:
        return
    if (x_ui_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


def _load_snapshots_via_provider(provider: BrokerReadProvider) -> List[BrokerSnapshot]:
    snaps: List[BrokerSnapshot] = []
    for acct in provider.list_accounts():
        snaps.append(provider.sync_snapshot(acct.alias))
    return snaps


def _try_live_or_empty_snapshots() -> List[BrokerSnapshot]:
    """Prefer last-good snapshot store; else empty list (honest, no invented balances)."""
    try:
        from app.core.broker import snapshot_store

        snaps: List[BrokerSnapshot] = []
        for alias in ("acct_individual", "acct_ira_roth", "acct_agentic"):
            loaded = snapshot_store.load_snapshot(alias)
            if loaded is not None:
                snaps.append(loaded)
        return snaps
    except Exception:
        return []


@router.get("/risk-v66")
def portfolio_risk_v66(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
    account_alias: Optional[str] = Query(None, description="Optional single-account filter"),
) -> Dict[str, Any]:
    """Account-aware risk dashboard. Never pools taxable/Roth/Agentic collateral."""
    _require_ui_key(x_ui_key)
    snaps = _try_live_or_empty_snapshots()
    if not snaps:
        # Empty but honest — do not invent positions/cash.
        result = evaluate_multi_account_risk([])
        result["status"] = "NO_SNAPSHOTS"
        result["message"] = "No last-good broker snapshots available. Sync read-only broker first."
        return result

    if account_alias:
        alias = account_alias.strip()
        snaps = [s for s in snaps if s.account_alias == alias]
        if not snaps:
            raise HTTPException(status_code=404, detail=f"No snapshot for alias {alias}")

    result = evaluate_multi_account_risk(snaps)
    result["status"] = "OK"
    return result


@router.post("/hedge-scenarios")
async def hedge_scenarios(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Manual hedge research scenarios for a single account."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    equity = body.get("portfolio_equity")
    try:
        equity_f = float(equity) if equity is not None else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="portfolio_equity must be numeric")
    return build_hedge_scenarios(
        account_alias=str(body.get("account_alias") or "acct_individual"),
        portfolio_equity=equity_f,
        downside_move_pct=float(body.get("downside_move_pct") or 0.10),
        hedge_etf=str(body.get("hedge_etf") or "SPY"),
        put_premium_pct=float(body.get("put_premium_pct") or 0.015),
        collar_call_credit_pct=float(body.get("collar_call_credit_pct") or 0.008),
        horizon_dte=int(body.get("horizon_dte") or 30),
    )


@router.get("/risk-v66/provider-contract")
def risk_provider_contract(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    """Document that risk uses BrokerReadProvider, not Robinhood-specific APIs."""
    _require_ui_key(x_ui_key)
    # Exercise FakeBrokerReadProvider to prove abstraction (no live MCP).
    fake: BrokerReadProvider = FakeBrokerReadProvider()
    aliases = [a.alias for a in fake.list_accounts()]
    return {
        "provider_interface": "BrokerReadProvider",
        "robinhood_specific": False,
        "demo_aliases": aliases,
        "schwab_status": "research_only",
        "schwab_doc": "docs/ai/research/SCHWAB_BROKER_READ_RESEARCH.md",
        "manual_only": True,
        "trade_execution": False,
    }
