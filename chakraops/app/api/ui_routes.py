# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Secured UI API: /api/ui/* — minimal surface for React frontend. LIVE vs MOCK separation."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.ui.live_dashboard_utils import list_decision_files, list_mock_files, load_decision_artifact

router = APIRouter(prefix="/api/ui", tags=["ui"])

UI_API_KEY = (os.getenv("UI_API_KEY") or "").strip()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _output_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        return Path(get_output_dir())
    except Exception:
        return _repo_root() / "out"


def _require_ui_key(x_ui_key: str | None = Header(None, alias="x-ui-key")) -> None:
    """If UI_API_KEY is set, require x-ui-key header. Otherwise allow (local dev)."""
    if not UI_API_KEY:
        return
    key = (x_ui_key or "").strip()
    if key != UI_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid x-ui-key")


def _validate_live_artifact(data: Dict[str, Any]) -> None:
    """LIVE mode: reject artifacts with data_source in (mock, scenario)."""
    ds = (data.get("data_source") or data.get("metadata", {}).get("data_source") or "").strip().lower()
    if ds in ("mock", "scenario"):
        raise HTTPException(
            status_code=400,
            detail=f"LIVE mode must not load mock/scenario data (data_source={ds})",
        )


Mode = Literal["LIVE", "MOCK"]


@router.get("/decision/files")
def ui_decision_files(
    mode: Mode = Query("LIVE", description="LIVE or MOCK"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    List decision files for the given mode.
    LIVE: out/ only; exclude decision_MOCK.json; exclude out/mock.
    MOCK: out/mock only.
    """
    _require_ui_key(x_ui_key)
    out_base = _output_dir()
    if mode == "LIVE":
        infos = list_decision_files(out_base, exclude_mock=True)
        out_dir = str(out_base)
    else:
        mock_dir = out_base / "mock"
        infos = list_mock_files(mock_dir)
        out_dir = str(mock_dir)

    files: List[Dict[str, Any]] = []
    for f in infos:
        try:
            mtime = datetime.fromtimestamp(f.modified_epoch_s, tz=timezone.utc)
            mtime_iso = mtime.isoformat()
        except (OSError, ValueError):
            mtime_iso = ""
        try:
            size = f.path.stat().st_size
        except OSError:
            size = 0
        files.append({
            "name": f.path.name,
            "mtime_iso": mtime_iso,
            "size_bytes": size,
        })
    return {"mode": mode, "dir": out_dir, "files": files}


@router.get("/decision/latest")
def ui_decision_latest(
    mode: Mode = Query("LIVE", description="LIVE or MOCK"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Get decision artifact (v2 preferred). ONE source of truth.
    LIVE: EvaluationStoreV2 / out/decision_latest.json (v2).
    MOCK: out/mock/decision_latest.json; 404 if absent.
    """
    _require_ui_key(x_ui_key)
    if mode == "LIVE":
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
        store = get_evaluation_store_v2()
        artifact = store.get_latest()
        if artifact is None:
            raise HTTPException(status_code=404, detail="No decision artifact (v2) in store. Run evaluation first.")
        return {"artifact": artifact.to_dict(), "artifact_version": "v2"}

    path = _output_dir() / "mock" / "decision_latest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No decision_latest.json for mode={mode}")
    data = load_decision_artifact(path)
    if data.get("metadata", {}).get("artifact_version") == "v2":
        return {"artifact": data, "artifact_version": "v2"}
    return data


@router.get("/decision/file/{filename}")
def ui_decision_file(
    filename: str,
    mode: Mode = Query("LIVE", description="LIVE or MOCK"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Get a specific decision file. Filename must be in the list returned by /decision/files.
    Prevents path traversal.
    """
    _require_ui_key(x_ui_key)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if mode == "LIVE":
        out_dir = _output_dir()
        infos = list_decision_files(out_dir, exclude_mock=True)
    else:
        out_dir = _output_dir() / "mock"
        infos = list_mock_files(out_dir)
    allowed = {f.path.name for f in infos}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail=f"File not found for mode={mode}")

    path = out_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    data = load_decision_artifact(path)
    if mode == "LIVE":
        _validate_live_artifact(data)
    return data


@router.get("/universe")
def ui_universe(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    UI-friendly universe: ONE source of truth from DecisionArtifactV2.
    Returns symbols array from artifact (no NOT_EVALUATED placeholders if eval has run).
    """
    _require_ui_key(x_ui_key)
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
        store = get_evaluation_store_v2()
        artifact = store.get_latest()
        meta = artifact.metadata or {} if artifact else {}
        ts = meta.get("pipeline_timestamp") or now_iso
        symbols_out: List[Dict[str, Any]] = []
        if artifact and artifact.symbols:
            for s in artifact.symbols:
                symbols_out.append({
                    "symbol": s.symbol,
                    "verdict": s.verdict,
                    "final_verdict": s.final_verdict,
                    "score": s.score,
                    "band": s.band,
                    "primary_reason": s.primary_reason or "",
                    "stage_status": s.stage_status,
                    "provider_status": s.provider_status or "n/a",
                    "data_freshness": s.data_freshness,
                    "strategy": s.strategy,
                    "price": s.price,
                    "expiration": s.expiration,
                    "score_breakdown": getattr(s, "score_breakdown", None),
                    "band_reason": getattr(s, "band_reason", None),
                    "max_loss": getattr(s, "max_loss", None),
                    "underlying_price": getattr(s, "underlying_price", None),
                })
        return {
            "source": "ARTIFACT_V2",
            "updated_at": ts,
            "as_of": ts,
            "symbols": symbols_out,
            "artifact_version": "v2",
        }
    except Exception as e:
        return {
            "source": "UNKNOWN",
            "updated_at": now_iso,
            "as_of": now_iso,
            "symbols": [],
            "error": str(e),
        }


@router.post("/eval/run")
def ui_eval_run(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Trigger evaluate_universe() — ONE engine, ONE store.
    Uses configured universe, stores into EvaluationStoreV2, writes decision_latest.json (v2).
    Returns {status, pipeline_timestamp, counts}.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.api.data_health import get_universe_symbols
        from app.core.eval.evaluation_service_v2 import evaluate_universe
        symbols = list(get_universe_symbols())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not symbols:
        return {"status": "FAILED", "reason": "Universe is empty", "pipeline_timestamp": None, "counts": {}}
    try:
        artifact = evaluate_universe(symbols, mode="LIVE")
        meta = artifact.metadata or {}
        return {
            "status": "OK",
            "pipeline_timestamp": meta.get("pipeline_timestamp"),
            "counts": {
                "universe_size": meta.get("universe_size", 0),
                "evaluated_count_stage1": meta.get("evaluated_count_stage1", 0),
                "evaluated_count_stage2": meta.get("evaluated_count_stage2", 0),
                "eligible_count": meta.get("eligible_count", 0),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-health")
def ui_system_health(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Aggregate system health for UI: api, orats, market, scheduler.
    Calls internal logic (healthz, data-health, market-status, scheduler) — single compact response.
    """
    _require_ui_key(x_ui_key)

    import time
    t0 = time.monotonic()

    # API: if we're here, API is up
    api_status = "OK"
    api_latency_ms: float | None = None

    # ORATS: data health
    orats_status = "UNKNOWN"
    orats_last_success: str | None = None
    orats_avg_latency: float | None = None
    orats_last_error: str | None = None
    try:
        from app.api.data_health import get_data_health
        dh = get_data_health()
        raw = (dh.get("status") or "UNKNOWN").upper()
        if raw == "OK":
            orats_status = "OK"
        elif raw in ("WARN", "DEGRADED"):
            orats_status = "WARN"
        elif raw == "DOWN":
            orats_status = "DOWN"
        orats_last_success = dh.get("last_success_at") or dh.get("effective_last_success_at")
        orats_avg_latency = dh.get("avg_latency_seconds")
        orats_last_error = dh.get("last_error_reason")
    except Exception:
        orats_status = "DOWN"
        orats_last_error = "Failed to read data health"

    # Market: phase, is_open
    market_phase = "UNKNOWN"
    market_is_open = False
    market_timestamp: str | None = None
    try:
        from app.market.market_hours import get_market_phase
        from app.api.market_status import read_market_status
        market_phase = get_market_phase() or "UNKNOWN"
        status = read_market_status()
        market_timestamp = status.get("last_market_check") or status.get("last_evaluated_at")
        market_is_open = market_phase == "OPEN"
    except Exception:
        pass

    api_latency_ms = round((time.monotonic() - t0) * 1000, 1)

    # Scheduler: placeholders if not available
    scheduler_interval: int | None = None
    scheduler_nightly_next: str | None = None
    scheduler_eod_next: str | None = None
    try:
        from app.api.server import get_scheduler_status, get_nightly_scheduler_status
        sched = get_scheduler_status()
        scheduler_interval = sched.get("interval_minutes")
        scheduler_nightly_next = None
        scheduler_eod_next = sched.get("next_expected_at")
        nightly = get_nightly_scheduler_status()
        scheduler_nightly_next = nightly.get("next_scheduled_at")
    except Exception:
        pass

    return {
        "api": {"status": api_status, "latency_ms": api_latency_ms},
        "orats": {
            "status": orats_status,
            "last_success_at": orats_last_success,
            "avg_latency_seconds": orats_avg_latency,
            "last_error_reason": orats_last_error,
        },
        "market": {
            "phase": market_phase,
            "is_open": market_is_open,
            "timestamp": market_timestamp,
        },
        "scheduler": {
            "interval_minutes": scheduler_interval,
            "nightly_next_at": scheduler_nightly_next,
            "eod_next_at": scheduler_eod_next,
        },
    }


@router.get("/accounts/default")
def ui_accounts_default(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Get the default account for manual execution. UI-safe wrapper for /api/accounts/default."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.service import get_default_account
        account = get_default_account()
        if account is None:
            return {"account": None, "message": "No default account set"}
        return {"account": account.to_dict()}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error getting default account: %s", e)
        return {"account": None, "message": str(e)}


@router.post("/positions/manual-execute")
async def ui_positions_manual_execute(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Record a manual execution (creates a tracked position). UI-safe wrapper."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import manual_execute
        body = await request.json()
        position, errors = manual_execute(body)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        return position.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error recording manual execution: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/portfolio")
def ui_portfolio(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Portfolio view: tracked positions with lifecycle (DTE, premium_captured %, alert flags).
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        from app.core.positions.lifecycle import enrich_position_for_portfolio
        positions = list_positions(status=None, symbol=None)
        mark_by_id: Dict[str, float] = {}
        underlying_by_symbol: Dict[str, float] = {}
        out: List[Dict[str, Any]] = [
            enrich_position_for_portfolio(p, mark_by_id, underlying_by_symbol)
            for p in positions
        ]
        return {"positions": out}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading portfolio: %s", e)
        return {"positions": []}


@router.get("/alerts")
def ui_alerts(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Alerts from portfolio positions (T1, T2, T3, DTE_RISK, STOP)."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        from app.core.positions.lifecycle import enrich_position_for_portfolio
        positions = list_positions(status=None, symbol=None)
        alerts: List[Dict[str, Any]] = []
        for p in positions:
            if (p.status or "").upper() not in ("OPEN", "PARTIAL_EXIT"):
                continue
            enriched = enrich_position_for_portfolio(p, None, None)
            for flag in enriched.get("alert_flags") or []:
                alerts.append({
                    "position_id": p.position_id,
                    "symbol": p.symbol,
                    "type": flag,
                    "message": f"{p.symbol} {flag}",
                })
        return {"alerts": alerts}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading alerts: %s", e)
        return {"alerts": []}


@router.get("/positions/tracked")
def ui_positions_tracked(
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    UI-safe wrapper for /api/positions/tracked.
    Returns { positions: [{ symbol, qty, contracts?, avg_price?, notional?, updated_at? }] }.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        positions = list_positions(status=status, symbol=symbol)
        out: List[Dict[str, Any]] = []
        for p in positions:
            d = p.to_dict()
            qty: int | None = None
            if (d.get("strategy") or "").upper() == "STOCK":
                qty = d.get("quantity")
            else:
                qty = d.get("contracts")
            avg_price = d.get("credit_expected")
            strike = d.get("strike")
            contracts = d.get("contracts") or 0
            notional = None
            if strike is not None and contracts:
                notional = float(strike) * 100 * int(contracts)
            out.append({
                "symbol": d.get("symbol", ""),
                "qty": qty,
                "contracts": d.get("contracts"),
                "avg_price": avg_price,
                "notional": notional,
                "updated_at": d.get("opened_at"),
                "status": d.get("status"),
            })
        return {"positions": out}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error listing tracked positions: %s", e)
        return {"positions": []}


def _build_symbol_diagnostics_from_v2_store(
    summary: Any,
    candidates: List[Any],
    gates: List[Any],
    earnings: Any | None,
    diagnostics_details: Any | None,
    symbol: str,
) -> Dict[str, Any]:
    """Build full SymbolDiagnosticsResponseExtended from v2 store (summary + candidates + gates + earnings + diagnostics_details)."""
    c_dicts = [c.to_dict() if hasattr(c, "to_dict") else (c if isinstance(c, dict) else {}) for c in candidates]
    g_list = [{"name": g.name, "status": g.status, "reason": g.reason, "pass": g.status == "PASS"} for g in gates] if gates else []
    diag = diagnostics_details
    if diag and hasattr(diag, "to_dict"):
        diag = diag.to_dict()
    diag = diag or {}
    technicals = diag.get("technicals") or {}
    exit_plan = diag.get("exit_plan") or {}
    risk_flags = diag.get("risk_flags") or {}
    explanation = diag.get("explanation") or {}
    stock = diag.get("stock") or {}
    symbol_eligibility = diag.get("symbol_eligibility") or {}
    liquidity = diag.get("liquidity") or {}
    earnings_out = None
    if earnings:
        earnings_out = {
            "earnings_days": getattr(earnings, "earnings_days", None),
            "earnings_block": getattr(earnings, "earnings_block", None),
            "note": getattr(earnings, "note", None) or "Not evaluated",
        }
    return {
        "symbol": symbol,
        "provider_status": getattr(summary, "provider_status", "OK") or "OK",
        "provider_message": "",
        "primary_reason": getattr(summary, "primary_reason", None),
        "verdict": getattr(summary, "verdict", "HOLD"),
        "in_universe": True,
        "stock": stock if stock else None,
        "explanation": explanation,
        "gates": g_list,
        "blockers": [],
        "notes": [],
        "symbol_eligibility": {
            "status": symbol_eligibility.get("status"),
            "required_data_missing": symbol_eligibility.get("required_data_missing") or [],
            "required_data_stale": symbol_eligibility.get("required_data_stale") or [],
            "reasons": symbol_eligibility.get("reasons") or [],
        },
        "liquidity": {
            "stock_liquidity_ok": liquidity.get("stock_liquidity_ok"),
            "option_liquidity_ok": liquidity.get("option_liquidity_ok"),
            "reason": liquidity.get("reason"),
        },
        "computed": {
            "rsi": technicals.get("rsi"),
            "atr": technicals.get("atr"),
            "atr_pct": technicals.get("atr_pct"),
            "support_level": technicals.get("support_level"),
            "resistance_level": technicals.get("resistance_level"),
        },
        "regime": diag.get("regime") or getattr(summary, "regime", None),
        "composite_score": getattr(summary, "score", None),
        "confidence_band": getattr(summary, "band", "D"),
        "suggested_capital_pct": diag.get("suggested_capital_pct"),
        "band_reason": getattr(summary, "band_reason", None),
        "candidates": c_dicts,
        "exit_plan": {"t1": exit_plan.get("t1"), "t2": exit_plan.get("t2"), "t3": exit_plan.get("t3"), "stop": exit_plan.get("stop")},
        "score_breakdown": diag.get("score_breakdown"),
        "rank_reasons": diag.get("rank_reasons"),
        "earnings": earnings_out,
    }


@router.get("/symbol-diagnostics")
def ui_symbol_diagnostics(
    symbol: str = Query(..., min_length=1, max_length=12),
    recompute: int = Query(0, description="1 to run single-symbol eval and update store"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Store-first symbol diagnostics. Default: serve from EvaluationStoreV2. recompute=1: run eval, update store, return result."""
    _require_ui_key(x_ui_key)
    sym_upper = symbol.strip().upper()

    if recompute:
        from app.core.eval.evaluation_service_v2 import evaluate_single_symbol_and_merge
        try:
            evaluate_single_symbol_and_merge(symbol=sym_upper)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Recompute failed: {e}")

    from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
    store = get_evaluation_store_v2()
    row = store.get_symbol(sym_upper)
    if row is not None:
        summary, candidates, gates, earnings, diagnostics_details = row
        return _build_symbol_diagnostics_from_v2_store(summary, candidates, gates, earnings, diagnostics_details, sym_upper)

    # Symbol not in store — 404 (no legacy path; use recompute=1 to add symbol)
    raise HTTPException(status_code=404, detail=f"Symbol {sym_upper} not in evaluation store. Use recompute=1 to evaluate.")
