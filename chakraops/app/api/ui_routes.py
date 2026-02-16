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
    Get decision_latest.json content.
    LIVE: out/decision_latest.json; validates data_source.
    MOCK: out/mock/decision_latest.json; 404 if absent.
    """
    _require_ui_key(x_ui_key)
    out_base = _output_dir()
    if mode == "LIVE":
        path = out_base / "decision_latest.json"
    else:
        path = out_base / "mock" / "decision_latest.json"

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No decision_latest.json for mode={mode}")

    data = load_decision_artifact(path)
    if mode == "LIVE":
        _validate_live_artifact(data)
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
    """UI-friendly universe snapshot: source, updated_at, as_of, symbols with key fields."""
    _require_ui_key(x_ui_key)
    from app.api.data_health import fetch_universe_from_canonical_snapshot
    from app.api.response_normalizers import normalize_universe_snapshot
    from app.market.market_hours import get_market_phase

    phase = get_market_phase()
    try:
        if phase == "OPEN":
            result = fetch_universe_from_canonical_snapshot()
            if result.get("all_failed"):
                return {
                    "source": "LIVE_COMPUTE",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "as_of": datetime.now(timezone.utc).isoformat(),
                    "symbols": [],
                }
            out = normalize_universe_snapshot({**result, "error": None, "source": "LIVE_COMPUTE"})
        else:
            from app.core.eval.run_artifacts import build_universe_from_latest_artifact
            artifact = build_universe_from_latest_artifact()
            if artifact:
                out = normalize_universe_snapshot({**artifact, "error": None, "source": "ARTIFACT_LATEST"})
            else:
                result = fetch_universe_from_canonical_snapshot()
                out = normalize_universe_snapshot({**result, "error": None, "source": "LIVE_COMPUTE_NO_ARTIFACT"})
    except Exception as e:
        return {
            "source": "LIVE_COMPUTE",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "as_of": datetime.now(timezone.utc).isoformat(),
            "symbols": [],
            "error": str(e),
        }

    updated = out.get("updated_at") or datetime.now(timezone.utc).isoformat()
    return {
        "source": out.get("source", "UNKNOWN"),
        "updated_at": updated,
        "as_of": updated,
        "symbols": out.get("symbols", []),
    }


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


@router.get("/symbol-diagnostics")
def ui_symbol_diagnostics(
    symbol: str = Query(..., min_length=1, max_length=12),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """UI-friendly symbol diagnostics: primary_reason, key fields, stage breakdown, execution confidence data."""
    _require_ui_key(x_ui_key)
    from app.api.symbol_diagnostics import get_symbol_diagnostics

    result = get_symbol_diagnostics(symbol=symbol)
    eligibility = result.get("eligibility") or {}
    symbol_eligibility = result.get("symbol_eligibility") or {}
    liquidity = result.get("liquidity") or {}

    # --- Eligibility trace computed (RSI, ATR, S/R) ---
    el_trace = result.get("eligibility_trace") or {}
    computed_in = el_trace.get("computed") or {}
    computed_out: Dict[str, Any] = {
        "rsi": el_trace.get("rsi14") or computed_in.get("RSI14"),
        "atr": computed_in.get("ATR14"),
        "atr_pct": el_trace.get("atr_pct") or computed_in.get("ATR_pct"),
        "support_level": el_trace.get("support_level") or computed_in.get("support_level"),
        "resistance_level": el_trace.get("resistance_level") or computed_in.get("resistance_level"),
    }

    # --- Staged evaluation: score, band, capital hint ---
    capital_hint = eligibility.get("capital_hint") or {}
    if isinstance(capital_hint, dict):
        confidence_band = capital_hint.get("band")
        suggested_capital_pct = capital_hint.get("suggested_capital_pct")
        band_reason = capital_hint.get("band_reason")
    else:
        confidence_band = getattr(capital_hint, "band", None)
        suggested_capital_pct = getattr(capital_hint, "suggested_capital_pct", None)
        band_reason = getattr(capital_hint, "band_reason", None)

    # --- Candidate contract list (already computed by evaluation) ---
    candidate_trades = result.get("candidate_trades") or []

    # --- Exit plan (T1, T2, T3, stop) from build_exit_plan using already-fetched data ---
    exit_plan_out: Dict[str, Any] = {"t1": None, "t2": None, "t3": None, "stop": None}
    try:
        from app.core.lifecycle.exit_planner import build_exit_plan

        spot = None
        stock = result.get("stock")
        if stock and isinstance(stock, dict):
            spot = stock.get("price")
        mode_decision = el_trace.get("mode_decision", "NONE")
        stage2_trace = result.get("stage2_trace") or {}

        ep = build_exit_plan(
            symbol=result.get("symbol", symbol),
            mode_decision=mode_decision,
            spot=spot,
            eligibility_trace=el_trace,
            stage2_trace=stage2_trace,
            candles_meta=None,
        )
        sp = (ep.get("structure_plan") or {}) if isinstance(ep, dict) else {}
        if sp:
            exit_plan_out["t1"] = sp.get("T1")
            exit_plan_out["t2"] = sp.get("T2")
            exit_plan_out["t3"] = sp.get("T3")
            exit_plan_out["stop"] = sp.get("stop_hint_price")
    except Exception:
        pass  # Exit plan optional; omit on error

    # --- Ranking: score_breakdown, rank_reasons ---
    score_breakdown = eligibility.get("score_breakdown")
    rank_reasons = eligibility.get("rank_reasons")

    # --- Provider status for empty/missing data (reduce UI confusion) ---
    options = result.get("options") or {}
    expirations_count = options.get("expirations_count", 0) if isinstance(options, dict) else 0
    provider_status = "OK"
    provider_message = ""
    if result.get("error"):
        provider_status = "ERROR"
        provider_message = str(result.get("error", ""))[:200]
    elif expirations_count == 0:
        provider_status = "NO_CHAIN"
        provider_message = "No option chain expirations available for this symbol."
    elif result.get("not_found") or result.get("provider_404"):
        provider_status = "NOT_FOUND"
        provider_message = result.get("provider_message") or "Symbol or quote data not found."

    # Phase 7.3: Structured explanation for symbol-diagnostics UI
    spot = None
    if result.get("stock") and isinstance(result["stock"], dict):
        spot = result["stock"].get("price")
    el_trace = result.get("eligibility_trace") or {}
    support = computed_out.get("support_level") or el_trace.get("support_level")
    support_condition = None
    if support is not None and isinstance(support, (int, float)):
        support_condition = f"Support ${float(support):.2f}" + (f" vs spot ${float(spot):.2f}" if spot is not None else "")
    liq_ok = liquidity.get("stock_liquidity_ok") and liquidity.get("option_liquidity_ok")
    explanation: Dict[str, Any] = {
        "stock_regime_reason": (el_trace.get("regime") or result.get("regime") or "").strip() or None,
        "support_condition": support_condition,
        "liquidity_condition": liquidity.get("reason") if not liq_ok else "OK",
        "iv_condition": eligibility.get("primary_reason") or None,
    }
    out: Dict[str, Any] = {
        "symbol": result.get("symbol"),
        "provider_status": provider_status,
        "provider_message": provider_message,
        "primary_reason": eligibility.get("primary_reason"),
        "verdict": eligibility.get("verdict"),
        "in_universe": result.get("in_universe"),
        "stock": result.get("stock"),
        "explanation": explanation,
        "gates": result.get("gates", []),
        "blockers": result.get("blockers", []),
        "notes": result.get("notes", []),
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
        # --- Execution confidence (all from already-computed evaluation) ---
        "computed": computed_out,
        "regime": el_trace.get("regime"),
        "composite_score": eligibility.get("score"),
        "confidence_band": confidence_band,
        "suggested_capital_pct": suggested_capital_pct,
        "band_reason": band_reason,
        "candidates": candidate_trades,
        "exit_plan": exit_plan_out,
        "score_breakdown": score_breakdown,
        "rank_reasons": rank_reasons,
    }
    return out
