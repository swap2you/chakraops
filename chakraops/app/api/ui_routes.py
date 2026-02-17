# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Secured UI API: /api/ui/* — minimal surface for React frontend. LIVE vs MOCK separation."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request

from app.ui.live_dashboard_utils import list_decision_files, list_mock_files, load_decision_artifact

router = APIRouter(prefix="/api/ui", tags=["ui"])

UI_API_KEY = (os.getenv("UI_API_KEY") or "").strip()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _output_dir() -> Path:
    """Canonical out dir = parent of decision_latest.json (ONE store)."""
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        return get_decision_store_path().parent
    except Exception:
        return _repo_root().parent / "out"


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
        store.reload_from_disk()
        artifact = store.get_latest()
        if artifact is None:
            raise HTTPException(status_code=404, detail="no v2 artifact; run evaluation")
        data = artifact.to_dict()
        _validate_live_artifact(data)
        return {"artifact": data, "artifact_version": "v2"}

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
        store.reload_from_disk()
        artifact = store.get_latest()
        meta = artifact.metadata or {} if artifact else {}
        ts = meta.get("pipeline_timestamp") or now_iso
        symbols_out: List[Dict[str, Any]] = []
        if artifact and artifact.symbols:
            diag_by_sym = getattr(artifact, "diagnostics_by_symbol", None) or {}
            for s in artifact.symbols:
                sym_key = (s.symbol or "").strip().upper()
                diag = diag_by_sym.get(sym_key)
                sel_el = (diag.symbol_eligibility or {}) if diag else {}
                score_caps = getattr(s, "score_caps", None)
                raw_score = getattr(s, "raw_score", None)
                row: Dict[str, Any] = {
                    "symbol": s.symbol,
                    "verdict": s.verdict,
                    "final_verdict": s.final_verdict,
                    "score": s.score,
                    "raw_score": raw_score,
                    "score_caps": score_caps,
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
                    "capital_required": getattr(s, "capital_required", None),
                    "expected_credit": getattr(s, "expected_credit", None),
                    "premium_yield_pct": getattr(s, "premium_yield_pct", None),
                    "market_cap": getattr(s, "market_cap", None),
                    "rank_score": getattr(s, "rank_score", None),
                }
                row["required_data_missing"] = sel_el.get("required_data_missing") or []
                row["required_data_stale"] = sel_el.get("required_data_stale") or []
                row["optional_missing"] = sel_el.get("optional_missing") or []
                symbols_out.append(row)
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

    # Scheduler: interval, heartbeat (last_run_at, next_run_at, last_result)
    scheduler_interval: int | None = None
    scheduler_nightly_next: str | None = None
    scheduler_eod_next: str | None = None
    scheduler_last_run_at: str | None = None
    scheduler_next_run_at: str | None = None
    scheduler_last_result: str | None = None
    try:
        from app.api.server import get_scheduler_status, get_nightly_scheduler_status
        sched = get_scheduler_status()
        scheduler_interval = sched.get("interval_minutes")
        scheduler_last_run_at = sched.get("last_run_at")
        scheduler_next_run_at = sched.get("next_run_at")
        scheduler_last_result = sched.get("last_result")
        scheduler_eod_next = sched.get("next_run_at")
        nightly = get_nightly_scheduler_status()
        scheduler_nightly_next = nightly.get("next_scheduled_at")
    except Exception:
        pass

    # Decision store (v2): CRITICAL if missing, not v2, band null. Include active_path and frozen.
    decision_store_status = "OK"
    decision_store_reason: str | None = None
    canonical_path_str: str | None = None
    active_path_str: str | None = None
    frozen_in_effect: bool = False
    try:
        from app.core.eval.evaluation_store_v2 import (
            get_evaluation_store_v2,
            get_decision_store_path,
            get_active_decision_path,
            _frozen_path,
        )
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        artifact = store.get_latest()
        store_path = get_decision_store_path()
        active_path = get_active_decision_path(market_phase)
        active_path_str = str(active_path)
        canonical_path_str = str(store_path)
        frozen_in_effect = active_path != store_path and _frozen_path().exists()
        if not active_path.exists():
            decision_store_status = "CRITICAL"
            decision_store_reason = "Active store file missing"
        elif artifact is None:
            decision_store_status = "CRITICAL"
            decision_store_reason = "No v2 artifact in store"
        else:
            meta = artifact.metadata or {}
            if meta.get("artifact_version") != "v2":
                decision_store_status = "CRITICAL"
                decision_store_reason = f"artifact_version={meta.get('artifact_version')}, expected v2"
            else:
                null_bands = [s for s in (artifact.symbols or []) if not s.band or s.band.strip() == ""]
                if null_bands:
                    decision_store_status = "CRITICAL"
                    decision_store_reason = f"{len(null_bands)} symbol(s) have null band"
        if decision_store_status == "OK" and (market_phase or "").upper() != "OPEN" and not _frozen_path().exists():
            decision_store_status = "WARN"
            decision_store_reason = "Market closed and no decision_frozen.json; serving decision_latest"
    except Exception as e:
        decision_store_status = "CRITICAL"
        decision_store_reason = str(e)

    return {
        "api": {"status": api_status, "latency_ms": api_latency_ms},
        "decision_store": {
            "status": decision_store_status,
            "reason": decision_store_reason,
            "canonical_path": canonical_path_str,
            "active_path": active_path_str,
            "frozen_in_effect": frozen_in_effect,
        },
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
            "last_run_at": scheduler_last_run_at,
            "next_run_at": scheduler_next_run_at,
            "last_result": scheduler_last_result,
        },
    }


@router.post("/diagnostics/run")
def ui_diagnostics_run(
    checks: str | None = Query(default=None, description="Comma-separated: orats,decision_store,universe,positions,scheduler"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Run sanity checks. Optional ?checks=a,b,c to run subset.
    Persists to out/diagnostics_history.jsonl.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.api.diagnostics import run_diagnostics, ALL_CHECKS
        check_set = None
        if checks and checks.strip():
            parts = [p.strip().lower() for p in checks.split(",") if p.strip()]
            check_set = {p for p in parts if p in ALL_CHECKS} or None
        return run_diagnostics(checks=check_set)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error running diagnostics: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics/history")
def ui_diagnostics_history(
    limit: int = Query(default=10, ge=1, le=100),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Return last N diagnostic runs (newest first)."""
    _require_ui_key(x_ui_key)
    try:
        from app.api.diagnostics import get_diagnostics_history
        runs = get_diagnostics_history(limit=limit)
        return {"runs": runs}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading diagnostics history: %s", e)
        return {"runs": []}


@router.get("/notifications")
def ui_notifications(
    limit: int = Query(default=100, ge=1, le=500),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Return last N notifications (newest first)."""
    _require_ui_key(x_ui_key)
    try:
        from app.api.notifications_store import load_notifications
        items = load_notifications(limit=limit)
        return {"notifications": items}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading notifications: %s", e)
        return {"notifications": []}


@router.post("/notifications")
async def ui_notifications_append(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Append a notification (for testing or external wiring)."""
    _require_ui_key(x_ui_key)
    try:
        from app.api.notifications_store import append_notification
        body = await request.json()
        severity = body.get("severity", "INFO")
        ntype = body.get("type", "USER")
        message = body.get("message", "")
        symbol = body.get("symbol")
        details = body.get("details") or {}
        append_notification(severity=severity, ntype=ntype, message=message, symbol=symbol, details=details)
        return {"status": "OK"}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error appending notification: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


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


@router.get("/positions")
def ui_positions_list(
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Get current positions (same data as /positions/tracked).
    Returns { positions: [{ symbol, qty, contracts?, notional?, updated_at?, status? }] }.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        positions = list_positions(status=status, symbol=symbol)
        out: List[Dict[str, Any]] = []
        for p in positions:
            d = p.to_dict()
            qty = d.get("quantity") if (d.get("strategy") or "").upper() == "STOCK" else d.get("contracts")
            strike = d.get("strike")
            contracts = d.get("contracts") or 0
            notional = (float(strike) * 100 * int(contracts)) if strike is not None and contracts else None
            out.append({
                "position_id": d.get("position_id"),
                "symbol": d.get("symbol", ""),
                "qty": qty,
                "contracts": d.get("contracts"),
                "avg_price": d.get("credit_expected"),
                "notional": notional,
                "updated_at": d.get("opened_at"),
                "status": d.get("status"),
            })
        return {"positions": out}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error listing positions: %s", e)
        return {"positions": []}


@router.post("/positions")
async def ui_positions_create(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Create a paper position from a candidate (symbol, strategy, contract details, credit, max_loss).
    Body: symbol, strategy, contracts?, strike?, expiration?, credit_expected?, decision_snapshot_id? (optional).
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import add_paper_position
        body = await request.json()
        position, errors = add_paper_position(body)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        return position.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error creating paper position: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


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


def _liquidity_evaluated(summary: Any) -> bool:
    """True if Stage2 ran and liquidity checks were evaluated; False if Stage2 did not run (NOT_EVALUATED)."""
    stage2_status = getattr(summary, "stage2_status", None) or ""
    return stage2_status != "NOT_RUN"


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
            "optional_missing": symbol_eligibility.get("optional_missing") or [],
            "reasons": symbol_eligibility.get("reasons") or [],
        },
        "liquidity": {
            "stock_liquidity_ok": liquidity.get("stock_liquidity_ok"),
            "option_liquidity_ok": liquidity.get("option_liquidity_ok"),
            "reason": liquidity.get("reason"),
            "missing_fields": liquidity.get("missing_fields") or [],
            "chain_missing_fields": liquidity.get("chain_missing_fields") or [],
            "liquidity_evaluated": _liquidity_evaluated(summary),
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
        "raw_score": getattr(summary, "raw_score", None),
        "score_caps": getattr(summary, "score_caps", None),
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
    store.reload_from_disk()
    row = store.get_symbol(sym_upper)
    if row is not None:
        summary, candidates, gates, earnings, diagnostics_details = row
        return _build_symbol_diagnostics_from_v2_store(summary, candidates, gates, earnings, diagnostics_details, sym_upper)

    # Symbol not in store — 404 (no legacy path; use recompute=1 to add symbol)
    raise HTTPException(status_code=404, detail=f"Symbol {sym_upper} not in evaluation store. Use recompute=1 to evaluate.")


@router.post("/symbols/{symbol}/recompute")
def ui_symbol_recompute(
    symbol: str = Path(..., min_length=1, max_length=12),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Run full evaluation for one symbol and merge into the canonical store.
    Updates decision_latest.json; Universe and Dashboard read from same store.
    Returns pipeline_timestamp and updated symbol summary so UI can refetch.
    """
    _require_ui_key(x_ui_key)
    sym_upper = symbol.strip().upper()
    try:
        from app.core.eval.evaluation_service_v2 import evaluate_single_symbol_and_merge
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
        merged = evaluate_single_symbol_and_merge(symbol=sym_upper)
    except Exception as e:
        try:
            from app.api.notifications_store import append_notification
            append_notification("WARN", "RECOMPUTE_FAILURE", str(e), symbol=sym_upper, details={"error": str(e)[:500]})
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Recompute failed: {e}")
    store = get_evaluation_store_v2()
    store.reload_from_disk()
    row = store.get_symbol(sym_upper)
    meta = (merged.metadata or {}) if merged else {}
    ts = meta.get("pipeline_timestamp") or ""
    result: Dict[str, Any] = {
        "symbol": sym_upper,
        "pipeline_timestamp": ts,
        "artifact_version": "v2",
        "updated": True,
    }
    if row is not None:
        summary, _candidates, _gates, _earnings, _diag = row
        result["score"] = summary.score
        result["band"] = summary.band
        result["verdict"] = summary.verdict
    return result
