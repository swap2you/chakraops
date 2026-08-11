# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R64–R69 go-live API surface (read-only / advisory)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.broker.runtime_status_r64 import classify_broker_runtime_status, sizing_allowed_for_broker
from app.core.broker.robinhood_mcp_client import resolve_access_token
from app.core.broker.snapshot_store import load_snapshot
from app.core.portfolio.risk_r66 import compute_account_risk, hedge_scenario
from app.core.universe.universe_v4_r67 import evaluate_candidate_v4
from app.core.strategy.builder_r68 import build_strategy_plan, csp_payoff
from app.core.backtest.calibration_r69 import label_regime, propose_calibration_change
from app.core.backtest.orats_backtest_probe_r59 import probe_orats_backtest_api
from app.core.monitor.advisory_worker_r54 import get_monitor_worker

router = APIRouter(prefix="/api/ui/golive", tags=["golive-r64-r69"])


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    import os

    expected = (os.getenv("UI_API_KEY") or "").strip()
    if not expected:
        return
    if (x_ui_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


@router.get("/broker/runtime-status")
def golive_broker_runtime_status(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    snap = load_snapshot("acct_individual")
    status = classify_broker_runtime_status(
        token_present=bool(resolve_access_token()),
        snapshot=snap.to_dict() if snap else None,
    )
    status["sizing_allowed"] = sizing_allowed_for_broker(status)
    status["deep_link_base"] = "https://chakraops.cloud"
    return status


@router.post("/risk/accounts")
async def golive_account_risk(request: Request, x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    body = await request.json()
    accounts = body.get("accounts") if isinstance(body, dict) else None
    if not isinstance(accounts, list):
        raise HTTPException(status_code=400, detail="accounts array required")
    return compute_account_risk(accounts)


@router.post("/risk/hedge-scenario")
async def golive_hedge(request: Request, x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return hedge_scenario(
        portfolio_equity=float(body.get("portfolio_equity") or 0),
        hedge_pct=float(body.get("hedge_pct") or 0.1),
        put_cost_pct=float(body.get("put_cost_pct") or 0.02),
    )


@router.post("/universe/v4/evaluate")
async def golive_universe_v4(request: Request, x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return evaluate_candidate_v4(dict(body.get("candidate") or {}), events=list(body.get("events") or []))


@router.post("/strategy/builder")
async def golive_strategy_builder(request: Request, x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return build_strategy_plan(
        capital=float(body.get("capital") or 0),
        account_alias=str(body.get("account_alias") or "acct_individual"),
        horizon_months=int(body.get("horizon_months") or 12),
        max_drawdown_pct=float(body.get("max_drawdown_pct") or 20),
        assignment_comfort=str(body.get("assignment_comfort") or "medium"),
        target_return_pct=body.get("target_return_pct"),
    )


@router.post("/strategy/csp-payoff")
async def golive_csp_payoff(request: Request, x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return csp_payoff(
        strike=float(body.get("strike") or 0),
        credit=float(body.get("credit") or 0),
        spot=float(body.get("spot") or 0),
    )


@router.get("/research/orats-backtest-probe")
def golive_orats_probe(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    return probe_orats_backtest_api()


@router.post("/research/calibration-propose")
async def golive_calibration(request: Request, x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return propose_calibration_change(
        parameter=str(body.get("parameter") or ""),
        current_value=body.get("current_value"),
        proposed_value=body.get("proposed_value"),
        evidence_refs=list(body.get("evidence_refs") or []),
    )


@router.get("/research/regime-label")
def golive_regime(
    period_start: str,
    period_end: str,
    proxy: bool = False,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    return label_regime(period_start, period_end, proxy=proxy)


@router.post("/monitor/run-once")
def golive_monitor_once(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> Dict[str, Any]:
    _require_ui_key(x_ui_key)
    signals = get_monitor_worker().run_once()
    return {
        "ok": True,
        "signals": [s.to_dict() for s in signals],
        "deep_link_base": "https://chakraops.cloud",
        "manual_only": True,
        "trade_execution": False,
    }
