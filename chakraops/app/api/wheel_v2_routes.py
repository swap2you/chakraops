# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 Wheel V2 decision API — advisory, manual-only, request-time enrichment."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query

router = APIRouter(prefix="/api/ui/wheel/v2", tags=["wheel-v2"])


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    expected = (os.getenv("UI_API_KEY") or "").strip()
    if not expected:
        return
    if (x_ui_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


def _portfolio_from_account(account: Any) -> Dict[str, Any]:
    total = float(getattr(account, "total_capital", None) or 0.0)
    cash = total
    try:
        from app.core.accounts.holdings_db import get_account_summary

        summary = get_account_summary()
        if isinstance(summary, dict):
            cash = float(summary.get("cash") or summary.get("buying_power") or cash)
            if summary.get("buying_power") is not None and float(summary.get("buying_power") or 0) > 0:
                # Prefer buying power when present for collateral checks
                cash = max(cash, float(summary.get("buying_power") or 0))
    except Exception:
        pass
    return {
        "total_value": total,
        "available_cash": cash,
        "cash": cash,
        "total_capital": total,
        "buying_power": cash,
    }


def _context_for_symbol(symbol: str) -> Dict[str, Any]:
    """Best-effort request-time context from evaluation store (no live ORATS)."""
    ctx: Dict[str, Any] = {"symbol": symbol}
    try:
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2

        store = get_evaluation_store_v2()
        store.reload_from_disk()
        artifact = store.get_latest()
        if artifact is None:
            return ctx
        summary = None
        if hasattr(artifact, "summaries_by_symbol"):
            summary = (artifact.summaries_by_symbol or {}).get(symbol)
        elif hasattr(artifact, "get_summary"):
            summary = artifact.get_summary(symbol)
        if summary is not None:
            ctx["stage1_status"] = getattr(summary, "stage1_status", None) or (
                summary.get("stage1_status") if isinstance(summary, dict) else None
            )
            ctx["price"] = getattr(summary, "price", None) or (
                summary.get("price") if isinstance(summary, dict) else None
            )
            ctx["regime"] = getattr(summary, "regime", None) or (
                summary.get("regime") if isinstance(summary, dict) else None
            )
            ctx["market_regime"] = ctx.get("regime")
            ctx["earnings_days"] = getattr(summary, "earnings_days", None) or (
                summary.get("earnings_days") if isinstance(summary, dict) else None
            )
        candidates = []
        if hasattr(artifact, "candidates_by_symbol"):
            candidates = (artifact.candidates_by_symbol or {}).get(symbol) or []
        if candidates:
            c = candidates[0]
            if isinstance(c, dict):
                ctx["contract"] = {
                    "strike": c.get("strike"),
                    "expiry": c.get("expiry") or c.get("expiration"),
                    "delta": c.get("delta"),
                    "premium": c.get("credit_estimate") or c.get("premium"),
                    "dte": c.get("dte"),
                    "strategy": c.get("strategy"),
                    "contracts": 1,
                }
                score = float(c.get("score") or 50)
            else:
                ctx["contract"] = {
                    "strike": getattr(c, "strike", None),
                    "expiry": getattr(c, "expiry", None) or getattr(c, "expiration", None),
                    "delta": getattr(c, "delta", None),
                    "premium": getattr(c, "credit_estimate", None) or getattr(c, "premium", None),
                    "dte": getattr(c, "dte", None),
                    "strategy": getattr(c, "strategy", None),
                    "contracts": 1,
                }
                score = float(getattr(c, "score", None) or 50)
            strat = (ctx["contract"].get("strategy") or "CSP").upper()
            if strat == "CSP":
                ctx["csp_eval"] = {
                    "eligible": True,
                    "eligibility": True,
                    "decision_status": "ACTIONABLE",
                    "score": score,
                    "selected_contract": ctx["contract"],
                    "capital_required": float(ctx["contract"].get("strike") or 0) * 100,
                    "contracts": 1,
                }
    except Exception:
        pass
    try:
        from app.core.accounts.holdings_db import get_share_position, _DEFAULT_ACCOUNT_ID

        pos = get_share_position(_DEFAULT_ACCOUNT_ID, symbol)
        if pos:
            qty = getattr(pos, "quantity", None) or (pos.get("quantity") if isinstance(pos, dict) else 0) or 0
            ctx["shares_held"] = int(qty)
    except Exception:
        pass
    return ctx


@router.get("/decision")
def ui_wheel_v2_decision(
    symbol: str = Query(..., description="Underlying symbol"),
    profile: str = Query("balanced", description="Strategy profile name"),
    account_id: Optional[str] = Query(None, description="Account ID; omit for default"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    R38: Wheel V2 advisory decision for one symbol (safe labels).
    Request-time only; does not write decision_latest.json.
    """
    _require_ui_key(x_ui_key)
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol required")

    from app.core.decision_engine.wheel_v2 import evaluate_wheel_v2

    portfolio: Dict[str, Any] = {"total_value": 0.0, "available_cash": 0.0}
    open_position = None
    wheel_state = None
    try:
        from app.core.accounts.store import get_account, get_default_account
        from app.core.positions.service import list_positions
        from app.core.wheel.state_store import load_state

        account = get_account(account_id.strip()) if account_id else None
        if account is None:
            account = get_default_account()
        if account is not None:
            portfolio = _portfolio_from_account(account)

        positions = list_positions(status=None, symbol=sym, exclude_test=True)
        open_pos = [
            p
            for p in positions
            if (getattr(p, "status", None) or "").upper() in ("OPEN", "PARTIAL_EXIT")
            and (getattr(p, "symbol", None) or "").upper() == sym
        ]
        if open_pos:
            open_position = open_pos[0]

        state_data = load_state()
        entry = (state_data.get("symbols") or {}).get(sym) or {}
        wheel_state = entry.get("state")
    except Exception:
        pass

    ctx = _context_for_symbol(sym)
    decision = evaluate_wheel_v2(
        symbol=sym,
        context=ctx,
        open_position=open_position,
        portfolio=portfolio,
        profile=profile,
        wheel_state=wheel_state,
    )
    out = decision.to_dict()
    # Ensure flags always present for clients.
    out["manual_only"] = True
    out["trade_execution"] = False
    return out
