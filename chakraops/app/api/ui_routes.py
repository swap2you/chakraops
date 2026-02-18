# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Secured UI API: /api/ui/* — minimal surface for React frontend. LIVE vs MOCK separation."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

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


def _get_eod_freeze_health() -> Dict[str, Any]:
    """EOD freeze status for system health (PR2)."""
    try:
        from app.api.server import get_eod_freeze_status
        return get_eod_freeze_status()
    except Exception:
        return {"enabled": False, "last_run_at_utc": None, "last_result": None, "last_snapshot_dir": None}


def _get_decision_store_mtime_utc() -> Optional[str]:
    """Return active decision store file mtime as ISO UTC string, or None."""
    try:
        from app.core.eval.evaluation_store_v2 import get_active_decision_path
        path = get_active_decision_path()
        if path.exists():
            mtime = path.stat().st_mtime
            return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except Exception:
        pass
    return None


@router.get("/decision")
def ui_decision(
    symbol: str | None = Query(default=None, description="Symbol for exact run fetch"),
    run_id: str | None = Query(default=None, description="Run ID for exact run fetch; requires symbol"),
    mode: Mode = Query("LIVE", description="LIVE or MOCK"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 11.2: Get decision artifact.
    If symbol and run_id provided: load from history; 404 if missing.
    If run_id absent: load latest (same as /decision/latest).
    """
    _require_ui_key(x_ui_key)
    if run_id and symbol:
        from app.core.eval.evaluation_store_v2 import get_decision_by_run
        artifact = get_decision_by_run(symbol.strip().upper(), run_id.strip())
        if artifact is None:
            raise HTTPException(status_code=404, detail="exact run not found")
        if mode != "LIVE":
            raise HTTPException(status_code=400, detail="exact run fetch only for LIVE mode")
        data = artifact.to_dict()
        _validate_live_artifact(data)
        meta = data.get("metadata") or {}
        pipeline_ts = meta.get("pipeline_timestamp")
        return {
            "artifact": data,
            "artifact_version": "v2",
            "evaluation_timestamp_utc": pipeline_ts,
            "run_id": meta.get("run_id"),
            "exact_run": True,
        }
    # Fall back to latest
    return _ui_decision_latest_impl(mode, x_ui_key)


def _ui_decision_latest_impl(
    mode: Mode,
    x_ui_key: str | None,
) -> Dict[str, Any]:
    """Shared logic for /decision/latest and /decision (no run_id)."""
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
        meta = data.get("metadata") or {}
        pipeline_ts = meta.get("pipeline_timestamp")
        store_mtime = _get_decision_store_mtime_utc()
        eval_ts = pipeline_ts if pipeline_ts else store_mtime
        result: Dict[str, Any] = {
            "artifact": data,
            "artifact_version": "v2",
            "evaluation_timestamp_utc": eval_ts,
            "decision_store_mtime_utc": store_mtime,
        }
        if meta.get("run_id"):
            result["run_id"] = meta["run_id"]
        return result

    path = _output_dir() / "mock" / "decision_latest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No decision_latest.json for mode={mode}")
    data = load_decision_artifact(path)
    if data.get("metadata", {}).get("artifact_version") == "v2":
        meta = data.get("metadata") or {}
        pipeline_ts = meta.get("pipeline_timestamp")
        store_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat() if path.exists() else None
        eval_ts = pipeline_ts if pipeline_ts else store_mtime
        return {"artifact": data, "artifact_version": "v2", "evaluation_timestamp_utc": eval_ts, "decision_store_mtime_utc": store_mtime}
    return data


@router.get("/decision/latest")
def ui_decision_latest(
    mode: Mode = Query("LIVE", description="LIVE or MOCK"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Get decision artifact (v2 preferred). ONE source of truth.
    LIVE: EvaluationStoreV2 / out/decision_latest.json (v2).
    MOCK: out/mock/decision_latest.json; 404 if absent.
    Phase 9: Includes evaluation_timestamp_utc (pipeline_timestamp or file mtime) and decision_store_mtime_utc.
    """
    return _ui_decision_latest_impl(mode, x_ui_key)


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
    meta = data.get("metadata") or {}
    pipeline_ts = meta.get("pipeline_timestamp")
    store_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    eval_ts = pipeline_ts if pipeline_ts else store_mtime
    return {**data, "evaluation_timestamp_utc": eval_ts, "decision_store_mtime_utc": store_mtime}


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
        sel_by_sym: Dict[str, Any] = {}
        for c in getattr(artifact, "selected_candidates", []) or []:
            sym_k = (getattr(c, "symbol", "") or "").strip().upper()
            if sym_k:
                sel_by_sym[sym_k] = c
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
                    "final_score": getattr(s, "final_score", None) or s.score,
                    "pre_cap_score": getattr(s, "pre_cap_score", None) or raw_score,
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
                sel_cand = sel_by_sym.get(sym_key)
                if sel_cand and (s.verdict or "").upper() == "ELIGIBLE":
                    row["selected_contract_key"] = getattr(sel_cand, "contract_key", None)
                    row["option_symbol"] = getattr(sel_cand, "option_symbol", None)
                    row["strike"] = getattr(sel_cand, "strike", None)
                symbols_out.append(row)
        store_mtime = _get_decision_store_mtime_utc()
        eval_ts = ts if ts else store_mtime
        out_d: Dict[str, Any] = {
            "source": "ARTIFACT_V2",
            "updated_at": ts,
            "as_of": ts,
            "evaluation_timestamp_utc": eval_ts,
            "decision_store_mtime_utc": store_mtime,
            "symbols": symbols_out,
            "artifact_version": "v2",
        }
        if meta.get("run_id"):
            out_d["run_id"] = meta["run_id"]
        return out_d
    except Exception as e:
        try:
            store_mtime = _get_decision_store_mtime_utc()
        except Exception:
            store_mtime = None
        return {
            "source": "UNKNOWN",
            "updated_at": now_iso,
            "as_of": now_iso,
            "evaluation_timestamp_utc": now_iso,
            "decision_store_mtime_utc": store_mtime,
            "symbols": [],
            "error": str(e),
        }


@router.get("/market/status")
def ui_market_status(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Market status for UI guardrails. Phase 9.
    Returns is_open, phase, now_utc, now_et, next_open_et, next_close_et.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.market.market_hours import get_market_phase, is_market_open, get_next_open_close_et
        now_utc = datetime.now(timezone.utc)
        phase = get_market_phase() or "UNKNOWN"
        market_open = is_market_open()
        try:
            from zoneinfo import ZoneInfo
            et_tz = ZoneInfo("America/New_York")
            now_et = now_utc.astimezone(et_tz).isoformat()
        except Exception:
            now_et = now_utc.isoformat()
        next_open_et, next_close_et = get_next_open_close_et(now_utc)
        return {
            "is_open": market_open,
            "phase": phase,
            "now_utc": now_utc.isoformat(),
            "now_et": now_et,
            "next_open_et": next_open_et,
            "next_close_et": next_close_et,
        }
    except Exception as e:
        return {
            "is_open": False,
            "phase": "UNKNOWN",
            "now_utc": datetime.now(timezone.utc).isoformat(),
            "now_et": None,
            "next_open_et": None,
            "next_close_et": None,
            "error": str(e),
        }


@router.post("/eval/run")
def ui_eval_run(
    force: bool = Query(False, description="Override market-closed guardrail"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Trigger evaluate_universe() — ONE engine, ONE store.
    Uses configured universe, stores into EvaluationStoreV2, writes decision_latest.json (v2).
    Phase 9: When market closed, returns 409 unless force=true.
    Returns {status, pipeline_timestamp, counts}.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.market.market_hours import get_market_phase
        phase = get_market_phase() or "OPEN"
        if phase != "OPEN" and not force:
            raise HTTPException(
                status_code=409,
                detail="Market is closed. Refusing to overwrite canonical decision. Use force=true to override.",
            )
        if phase != "OPEN" and force:
            import logging
            logging.getLogger(__name__).info("[EVAL] Run evaluation with force=true (market phase=%s)", phase)
    except HTTPException:
        raise
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


@router.post("/scheduler/run_once")
def ui_scheduler_run_once(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Trigger one scheduler tick. Same logic as background scheduler.
    Does NOT overwrite decision when market closed (returns started=False).
    Phase 10.2.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.api.server import run_scheduler_once
        return run_scheduler_once()
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error running scheduler once: %s", e)
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

    # ORATS: data health (Phase 9: age_minutes, staleness_threshold for actionable UI)
    orats_status = "UNKNOWN"
    orats_last_success: str | None = None
    orats_avg_latency: float | None = None
    orats_last_error: str | None = None
    orats_age_minutes: float | None = None
    orats_staleness_minutes: int = 30
    try:
        from app.api.data_health import get_data_health
        from app.core.config.eval_config import EVALUATION_QUOTE_WINDOW_MINUTES
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
        try:
            orats_staleness_minutes = int(EVALUATION_QUOTE_WINDOW_MINUTES)
        except (TypeError, ValueError):
            orats_staleness_minutes = 30
        if orats_last_success:
            try:
                success_dt = datetime.fromisoformat(orats_last_success.replace("Z", "+00:00"))
                orats_age_minutes = (datetime.now(timezone.utc) - success_dt).total_seconds() / 60
            except (ValueError, TypeError):
                pass
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
    decision_eval_ts: str | None = None
    decision_store_mtime: str | None = None
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
        eval_ts = (artifact.metadata or {}).get("pipeline_timestamp") if artifact else None
        store_mtime = _get_decision_store_mtime_utc()
        decision_eval_ts = eval_ts or store_mtime
        decision_store_mtime = store_mtime
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
            "evaluation_timestamp_utc": decision_eval_ts,
            "decision_store_mtime_utc": decision_store_mtime,
        },
        "orats": {
            "status": orats_status,
            "last_success_at": orats_last_success,
            "last_success_at_utc": orats_last_success,
            "age_minutes": round(orats_age_minutes, 1) if orats_age_minutes is not None else None,
            "staleness_threshold_minutes": orats_staleness_minutes,
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
        "eod_freeze": _get_eod_freeze_health(),
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


@router.post("/snapshots/freeze")
def ui_snapshots_freeze(
    skip_eval: bool = Query(False, description="Archive only, no evaluation"),
    force_eval: bool = Query(False, description="Force eval when timing edge blocks (rare)"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    EOD freeze snapshot. Market-aware: eval+archive only during OPEN before 4 PM ET; else archive_only.
    Never runs eval after market close. Returns {status, mode_used, snapshot_dir, manifest, ran_eval, eval_result?}.
    """
    _require_ui_key(x_ui_key)
    import logging
    log = logging.getLogger(__name__)
    now_utc = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo("America/New_York")
    except Exception:
        et_tz = timezone.utc
    now_et = now_utc.astimezone(et_tz)
    et_hour = now_et.hour + now_et.minute / 60.0 + now_et.second / 3600.0

    from app.market.market_hours import get_market_phase
    phase = get_market_phase(now_utc) or "UNKNOWN"
    market_open = phase == "OPEN"
    before_4pm_et = et_hour < 16.0

    ran_eval = False
    eval_result: Dict[str, Any] | None = None

    if market_open and before_4pm_et and not skip_eval:
        mode_used = "eval_then_archive"
        try:
            from app.api.data_health import get_universe_symbols
            from app.core.eval.evaluation_service_v2 import evaluate_universe
            symbols = list(get_universe_symbols())
            if symbols:
                artifact = evaluate_universe(symbols, mode="LIVE")
                ran_eval = True
                meta = artifact.metadata or {}
                eval_result = {
                    "pipeline_timestamp": meta.get("pipeline_timestamp"),
                    "counts": {
                        "universe_size": meta.get("universe_size", 0),
                        "evaluated_count_stage1": meta.get("evaluated_count_stage1", 0),
                        "evaluated_count_stage2": meta.get("evaluated_count_stage2", 0),
                        "eligible_count": meta.get("eligible_count", 0),
                    },
                }
                log.info("[FREEZE] Ran evaluation as part of freeze: %s symbols", len(symbols))
        except Exception as e:
            log.warning("[FREEZE] Eval failed, proceeding with archive_only: %s", e)
            mode_used = "archive_only"
    elif force_eval and market_open and not skip_eval:
        mode_used = "eval_then_archive"
        try:
            from app.api.data_health import get_universe_symbols
            from app.core.eval.evaluation_service_v2 import evaluate_universe
            symbols = list(get_universe_symbols())
            if symbols:
                artifact = evaluate_universe(symbols, mode="LIVE")
                ran_eval = True
                meta = artifact.metadata or {}
                eval_result = {"pipeline_timestamp": meta.get("pipeline_timestamp"), "counts": meta}
                log.info("[FREEZE] Ran evaluation (force_eval) as part of freeze")
        except Exception as e:
            log.warning("[FREEZE] Eval (force_eval) failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Force eval failed: {e}")
    else:
        mode_used = "archive_only"

    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out_dir = get_decision_store_path().parent
        decision_path = get_decision_store_path()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    from app.core.snapshots.freeze import run_freeze_snapshot
    result = run_freeze_snapshot(
        out_dir=out_dir,
        decision_store_path=decision_path,
        extra_paths=[],
        mode="archive_only",
        now_utc=now_utc,
    )
    return {
        "status": "OK",
        "mode_used": mode_used,
        "snapshot_dir": result["snapshot_dir"],
        "manifest": result["manifest"],
        "ran_eval": ran_eval,
        "eval_result": eval_result,
    }


@router.get("/snapshots/latest")
def ui_snapshots_latest(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Find latest snapshot folder in out/snapshots/*_eod. Returns manifest + path. 404 if none."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out_dir = get_decision_store_path().parent
    except Exception:
        out_dir = _repo_root().parent / "out"
    snap_base = out_dir / "snapshots"
    if not snap_base.exists():
        raise HTTPException(status_code=404, detail="No snapshots directory. Run freeze first.")
    dirs = [d for d in snap_base.iterdir() if d.is_dir() and d.name.endswith("_eod")]
    if not dirs:
        raise HTTPException(status_code=404, detail="No EOD snapshots found. Run freeze first.")
    manifest_path = None
    latest_dir = None
    latest_mtime = 0.0
    for d in dirs:
        mp = d / "snapshot_manifest.json"
        if mp.exists():
            mtime = mp.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_dir = d
                manifest_path = mp
    if latest_dir is None or manifest_path is None:
        raise HTTPException(status_code=404, detail="No snapshot manifest found. Run freeze first.")
    import json
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    return {"snapshot_dir": str(latest_dir), "manifest": manifest}


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
        subtype = body.get("subtype")
        append_notification(severity=severity, ntype=ntype, message=message, symbol=symbol, details=details, subtype=subtype)
        return {"status": "OK"}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error appending notification: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/notifications/{notification_id}/ack")
async def ui_notification_ack(
    notification_id: str,
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 10.3: Acknowledge a notification (append-only ack event)."""
    _require_ui_key(x_ui_key)
    if not notification_id or not notification_id.strip():
        raise HTTPException(status_code=400, detail="notification_id required")
    ack_by = "ui"
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        body = {}
    if isinstance(body, dict) and body.get("ack_by"):
        ack_by = str(body["ack_by"])[:64]
    try:
        from app.api.notifications_store import append_ack
        append_ack(ref_id=notification_id.strip(), ack_by=ack_by)
        return {"status": "OK", "ack_at_utc": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error acking notification: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/accounts")
def ui_accounts_list(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """List all accounts. Phase 10.0."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.service import list_accounts
        accounts = list_accounts()
        return {"accounts": [a.to_dict() for a in accounts]}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error listing accounts: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts")
async def ui_accounts_create(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Create a new account. Phase 10.0. Body: provider, account_type, total_capital, max_capital_per_trade_pct, max_total_exposure_pct, allowed_strategies."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.service import create_account
        body = await request.json()
        account, errors = create_account(body)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        return account.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error creating account: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


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
    exclude_test: bool = Query(default=True),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Portfolio view: tracked positions with lifecycle (DTE, premium_captured %, alert flags).
    Phase 10.0: Excludes is_test by default; adds capital_deployed and open_positions_count.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        from app.core.positions.lifecycle import enrich_position_for_portfolio
        positions = list_positions(status=None, symbol=None, exclude_test=exclude_test)
        mark_by_id: Dict[str, float] = {}
        underlying_by_symbol: Dict[str, float] = {}
        capital_deployed = 0.0
        open_count = 0
        out: List[Dict[str, Any]] = []
        for p in positions:
            enriched = enrich_position_for_portfolio(p, mark_by_id, underlying_by_symbol)
            collateral = getattr(p, "collateral", None)
            s = (p.status or "").upper()
            if s in ("OPEN", "PARTIAL_EXIT"):
                open_count += 1
                if collateral is not None:
                    capital_deployed += float(collateral)
                elif p.strike and p.contracts:
                    capital_deployed += float(p.strike) * 100 * int(p.contracts)
            out.append(enriched)
        return {
            "positions": out,
            "capital_deployed": round(capital_deployed, 2),
            "open_positions_count": open_count,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading portfolio: %s", e)
        return {"positions": [], "capital_deployed": 0, "open_positions_count": 0}


@router.get("/portfolio/metrics")
def ui_portfolio_metrics(
    account_id: str | None = Query(default=None, description="Filter by account_id; omit for all"),
    exclude_test: bool = Query(default=True),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 12.0: Portfolio metrics.
    Returns: open_positions_count, capital_deployed, realized_pnl_total, win_rate, avg_pnl, avg_credit, avg_dte_at_entry.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        from app.core.positions.lifecycle import enrich_position_for_portfolio
        positions = list_positions(status=None, symbol=None, exclude_test=exclude_test)
        if account_id:
            positions = [p for p in positions if (p.account_id or "").strip() == account_id.strip()]
        capital_deployed = 0.0
        open_count = 0
        closed = [p for p in positions if (p.status or "").upper() in ("CLOSED", "ABORTED")]
        realized_total = 0.0
        wins = 0
        pnls: List[float] = []
        credits: List[float] = []
        dtes: List[int] = []
        for p in positions:
            s = (p.status or "").upper()
            if s in ("OPEN", "PARTIAL_EXIT"):
                open_count += 1
                c = getattr(p, "collateral", None)
                if c is not None:
                    capital_deployed += float(c)
                elif p.strike and p.contracts:
                    capital_deployed += float(p.strike) * 100 * int(p.contracts)
        for p in closed:
            rp = getattr(p, "realized_pnl", None)
            if rp is not None:
                rv = float(rp)
                realized_total += rv
                pnls.append(rv)
                if rv > 0:
                    wins += 1
            oc = p.open_credit or p.credit_expected
            if oc is not None:
                credits.append(float(oc))
            # DTE at entry: days from opened_at to expiration (for closed, use expiration - open date)
            dte_at_entry: int | None = None
            if p.expiration and p.opened_at:
                try:
                    from datetime import datetime
                    exp = datetime.strptime(str(p.expiration).strip()[:10], "%Y-%m-%d").date()
                    opened = datetime.fromisoformat(str(p.opened_at).replace("Z", "+00:00")).date()
                    dte_at_entry = (exp - opened).days
                except (ValueError, TypeError):
                    pass
            if dte_at_entry is not None:
                dtes.append(dte_at_entry)
        win_rate = (wins / len(closed)) if closed else None
        avg_pnl = (sum(pnls) / len(pnls)) if pnls else None
        avg_credit = (sum(credits) / len(credits)) if credits else None
        avg_dte_at_entry = (sum(dtes) / len(dtes)) if dtes else None
        return {
            "open_positions_count": open_count,
            "capital_deployed": round(capital_deployed, 2),
            "realized_pnl_total": round(realized_total, 2),
            "win_rate": round(win_rate, 4) if win_rate is not None else None,
            "avg_pnl": round(avg_pnl, 2) if avg_pnl is not None else None,
            "avg_credit": round(avg_credit, 2) if avg_credit is not None else None,
            "avg_dte_at_entry": round(avg_dte_at_entry, 1) if avg_dte_at_entry is not None else None,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading portfolio metrics: %s", e)
        return {
            "open_positions_count": 0,
            "capital_deployed": 0,
            "realized_pnl_total": 0,
            "win_rate": None,
            "avg_pnl": None,
            "avg_credit": None,
            "avg_dte_at_entry": None,
        }


@router.get("/portfolio/risk")
def ui_portfolio_risk(
    account_id: str | None = Query(default=None, description="Account ID; omit for default"),
    exclude_test: bool = Query(default=True),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 14.0: Portfolio risk evaluation against account limits.
    Returns: {status: PASS|WARN|FAIL, metrics: {...}, breaches: [...]}.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.store import get_account, get_default_account
        from app.core.positions.service import list_positions
        from app.core.portfolio.risk import evaluate_portfolio_risk
        account = None
        if account_id:
            account = get_account(account_id.strip())
        if account is None:
            account = get_default_account()
        if account is None:
            return {"status": "FAIL", "metrics": {}, "breaches": [], "error": "No account found"}
        positions = list_positions(status=None, symbol=None, exclude_test=exclude_test)
        if account_id:
            positions = [p for p in positions if (p.account_id or "").strip() == account_id.strip()]
        open_pos = [p for p in positions if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT")]
        result = evaluate_portfolio_risk(account, open_pos)
        result["account_id"] = account.account_id
        return result
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error evaluating portfolio risk: %s", e)
        return {"status": "FAIL", "metrics": {}, "breaches": [], "error": str(e)}


@router.post("/positions/marks/refresh")
def ui_positions_marks_refresh(
    account_id: str | None = Query(default=None, description="Account ID; omit for all"),
    exclude_test: bool = Query(default=True),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 15.0: Refresh marks for OPEN positions from provider. Returns {updated_count, skipped_count, errors}.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        from app.core.portfolio.marking import refresh_marks
        positions = list_positions(status=None, symbol=None, exclude_test=exclude_test)
        if account_id:
            positions = [p for p in positions if (p.account_id or "").strip() == account_id.strip()]
        open_pos = [p for p in positions if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT")]
        updated, skipped, errors = refresh_marks(open_pos, account_id=account_id)
        return {"updated_count": updated, "skipped_count": skipped, "errors": errors}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error refreshing marks: %s", e)
        return {"updated_count": 0, "skipped_count": 0, "errors": [str(e)]}


@router.get("/portfolio/mtm")
def ui_portfolio_mtm(
    account_id: str | None = Query(default=None, description="Account ID; omit for all"),
    exclude_test: bool = Query(default=True),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 15.0: Portfolio MTM — totals + per-position unrealized_pnl.
    unrealized_pnl = open_credit - mark_debit_total - open_fees.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        from app.core.positions.lifecycle import enrich_position_for_portfolio
        positions = list_positions(status=None, symbol=None, exclude_test=exclude_test)
        if account_id:
            positions = [p for p in positions if (p.account_id or "").strip() == account_id.strip()]
        realized_total = 0.0
        unrealized_total = 0.0
        per_position: List[Dict[str, Any]] = []
        for p in positions:
            enriched = enrich_position_for_portfolio(p, None, None)
            d = {
                "position_id": p.position_id,
                "symbol": p.symbol,
                "status": p.status,
                "mark": enriched.get("mark"),
                "unrealized_pnl": enriched.get("unrealized_pnl"),
                "realized_pnl": getattr(p, "realized_pnl", None),
            }
            per_position.append(d)
            if (p.status or "").upper() in ("CLOSED", "ABORTED") and getattr(p, "realized_pnl", None) is not None:
                realized_total += float(p.realized_pnl)
            if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT") and enriched.get("unrealized_pnl") is not None:
                unrealized_total += float(enriched["unrealized_pnl"])
        return {
            "realized_total": round(realized_total, 2),
            "unrealized_total": round(unrealized_total, 2),
            "positions": per_position,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading portfolio MTM: %s", e)
        return {"realized_total": 0, "unrealized_total": 0, "positions": []}


@router.get("/alerts")
def ui_alerts(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Alerts from portfolio positions (T1, T2, T3, DTE_RISK, STOP)."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        from app.core.positions.lifecycle import enrich_position_for_portfolio
        positions = list_positions(status=None, symbol=None, exclude_test=True)
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
    exclude_test: bool = Query(default=True),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Get current positions. Phase 10.0: includes id, collateral, is_test; excludes test by default.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        positions = list_positions(status=status, symbol=symbol, exclude_test=exclude_test)
        out: List[Dict[str, Any]] = []
        for p in positions:
            d = p.to_dict()
            strike = d.get("strike")
            contracts = d.get("contracts") or 0
            collateral = d.get("collateral")
            notional = collateral
            if notional is None and strike is not None and contracts:
                notional = float(strike) * 100 * int(contracts)
            out.append({
                "position_id": d.get("position_id"),
                "id": d.get("id") or d.get("position_id"),
                "symbol": d.get("symbol", ""),
                "qty": d.get("quantity") if (d.get("strategy") or "").upper() == "STOCK" else d.get("contracts"),
                "contracts": d.get("contracts"),
                "avg_price": d.get("credit_expected") or d.get("open_credit"),
                "collateral": collateral,
                "notional": notional,
                "updated_at": d.get("updated_at_utc") or d.get("opened_at"),
                "status": d.get("status"),
                "is_test": d.get("is_test", False),
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
    Create a paper position from a candidate.
    Phase 11.0: Requires contract identity (symbol, strategy, strike, expiration, contracts).
    Optional: option_symbol, contract_key, decision_ref, open_credit, open_price, open_time_utc.
    Returns 409 when sizing limits exceeded (max_collateral_per_trade, max_total_collateral, max_positions_open).
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import add_paper_position
        body = await request.json()
        position, errors, status_code = add_paper_position(body)
        if errors:
            raise HTTPException(status_code=status_code, detail={"errors": errors})
        return position.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error creating paper position: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/positions/{position_id}/close")
async def ui_positions_close(
    position_id: str,
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Close an OPEN position. Phase 10.0. Body: close_price (required), close_time_utc? (optional), close_fees? (optional)."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import close_position
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body or {}
        close_price = body.get("close_price")
        if close_price is None:
            raise HTTPException(status_code=400, detail="close_price is required")
        try:
            close_price = float(close_price)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="close_price must be a number")
        close_time_utc = body.get("close_time_utc")
        close_fees = body.get("close_fees")
        position, errors = close_position(position_id, close_price, close_time_utc, close_fees)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        if position is None:
            raise HTTPException(status_code=404, detail="Position not found")
        return position.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error closing position: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/positions/{position_id}/decision")
def ui_position_decision(
    position_id: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 11.1/11.2: Get decision for a position.
    If position has decision_ref.run_id: try load from history -> exact_run=true; if missing -> exact_run=false + warning, return latest.
    If no run_id: exact_run=false + warning, return latest.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import get_position
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2, get_decision_by_run
        position = get_position(position_id)
        if position is None:
            raise HTTPException(status_code=404, detail="Position not found")
        decision_ref = getattr(position, "decision_ref", None) or {}
        if not isinstance(decision_ref, dict):
            decision_ref = {}
        run_id = decision_ref.get("run_id")
        sym = (getattr(position, "symbol", "") or "").strip().upper()
        artifact = None
        exact_run = False
        if run_id and sym:
            artifact = get_decision_by_run(sym, run_id)
            if artifact is not None:
                exact_run = True
        if artifact is None:
            store = get_evaluation_store_v2()
            store.reload_from_disk()
            artifact = store.get_latest()
        if artifact is None:
            raise HTTPException(status_code=404, detail="No decision artifact; run evaluation")
        data = artifact.to_dict()
        meta = data.get("metadata") or {}
        result: Dict[str, Any] = {
            "artifact": data,
            "artifact_version": "v2",
            "evaluation_timestamp_utc": meta.get("pipeline_timestamp") or meta.get("evaluation_timestamp_utc"),
            "run_id": meta.get("run_id"),
            "exact_run": exact_run,
        }
        if not exact_run and run_id:
            result["warning"] = "exact run not available; showing latest decision"
        elif not run_id:
            result["warning"] = "exact run not available; position has no run_id"
        return result
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading position decision: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/{position_id}/events")
def ui_position_events(
    position_id: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 13.0: Get lifecycle events for a position (OPEN, FILL, ADJUST, CLOSE, ABORT, NOTE)."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import get_position
        from app.core.positions.events_store import load_events_for_position
        position = get_position(position_id)
        if position is None:
            raise HTTPException(status_code=404, detail="Position not found")
        events = load_events_for_position(position_id)
        return {"position_id": position_id, "events": events}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading position events: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/{position_id}/roll")
async def ui_positions_roll(
    position_id: str,
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 13.0: Roll — close old position and open new with parent_position_id. Body: new contract_key/option_symbol, strike, expiration, contracts, close_debit, open_credit."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import roll_position
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body or {}
        contract_key = body.get("contract_key")
        option_symbol = body.get("option_symbol")
        strike = body.get("strike")
        expiration = body.get("expiration") or body.get("expiry")
        contracts = int(body.get("contracts", 1))
        close_debit = float(body.get("close_debit", 0))
        open_credit = float(body.get("open_credit", 0))
        if not contract_key and not option_symbol:
            raise HTTPException(status_code=400, detail="contract_key or option_symbol required")
        new_pos, errors = roll_position(
            position_id,
            new_contract_key=contract_key or "",
            new_option_symbol=option_symbol,
            new_strike=float(strike or 0),
            new_expiration=expiration or "",
            new_contracts=contracts,
            close_debit=close_debit,
            open_credit=open_credit,
        )
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        if new_pos is None:
            raise HTTPException(status_code=404, detail="Position not found")
        return {"closed_position_id": position_id, "new_position": new_pos.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error rolling position: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/positions/{position_id}")
def ui_positions_delete(
    position_id: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Delete a position. Phase 10.0. Allowed only when is_test=true OR status=CLOSED/ABORTED. Returns 409 otherwise."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import delete_position
        ok, err = delete_position(position_id)
        if not ok:
            status = 409 if err and "Delete allowed only" in err else 404
            raise HTTPException(status_code=status, detail=err or "Not found")
        return {"deleted": position_id}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error deleting position: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/tracked")
def ui_positions_tracked(
    status: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    exclude_test: bool = Query(default=True),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    UI-safe wrapper for /api/positions/tracked. Phase 10.0.
    Returns { positions, capital_deployed, open_positions_count }.
    Uses collateral for options (not notional). Excludes is_test by default.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        positions = list_positions(status=status, symbol=symbol, exclude_test=exclude_test)
        out: List[Dict[str, Any]] = []
        capital_deployed = 0.0
        open_count = 0
        for p in positions:
            d = p.to_dict()
            qty: int | None = None
            if (d.get("strategy") or "").upper() == "STOCK":
                qty = d.get("quantity")
            else:
                qty = d.get("contracts")
            avg_price = d.get("credit_expected") or d.get("open_credit")
            strike = d.get("strike")
            contracts = d.get("contracts") or 0
            collateral = d.get("collateral")
            notional = collateral
            if notional is None and strike is not None and contracts:
                notional = float(strike) * 100 * int(contracts)
            s = (d.get("status") or "").upper()
            if s in ("OPEN", "PARTIAL_EXIT"):
                open_count += 1
                if collateral is not None:
                    capital_deployed += float(collateral)
                elif notional is not None:
                    capital_deployed += float(notional)
            out.append({
                "id": d.get("id") or d.get("position_id"),
                "symbol": d.get("symbol", ""),
                "qty": qty,
                "contracts": d.get("contracts"),
                "avg_price": avg_price,
                "collateral": collateral,
                "notional": notional,
                "updated_at": d.get("updated_at_utc") or d.get("opened_at"),
                "status": d.get("status"),
                "is_test": d.get("is_test", False),
            })
        return {
            "positions": out,
            "capital_deployed": round(capital_deployed, 2),
            "open_positions_count": open_count,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error listing tracked positions: %s", e)
        return {"positions": [], "capital_deployed": 0, "open_positions_count": 0}


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
    selected_contract_key: Optional[str] = None,
    option_symbol: Optional[str] = None,
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
        "final_score": getattr(summary, "final_score", None) or getattr(summary, "score", None),
        "pre_cap_score": getattr(summary, "pre_cap_score", None) or getattr(summary, "raw_score", None),
        "score_caps": getattr(summary, "score_caps", None),
        "confidence_band": getattr(summary, "band", "D"),
        "suggested_capital_pct": diag.get("suggested_capital_pct"),
        "band_reason": getattr(summary, "band_reason", None),
        "candidates": c_dicts,
        "exit_plan": {"t1": exit_plan.get("t1"), "t2": exit_plan.get("t2"), "t3": exit_plan.get("t3"), "stop": exit_plan.get("stop")},
        "score_breakdown": diag.get("score_breakdown"),
        "rank_reasons": diag.get("rank_reasons"),
        "earnings": earnings_out,
        "selected_contract_key": selected_contract_key,
        "option_symbol": option_symbol,
    }


@router.get("/symbol-diagnostics")
def ui_symbol_diagnostics(
    symbol: str = Query(..., min_length=1, max_length=12),
    run_id: str | None = Query(default=None, description="Phase 11.2: Fetch from history for this run; fallback to latest if missing"),
    recompute: int = Query(0, description="1 to run single-symbol eval and update store"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Store-first symbol diagnostics. run_id: try history first. recompute=1: run eval, update store."""
    _require_ui_key(x_ui_key)
    sym_upper = symbol.strip().upper()

    if recompute:
        from app.core.eval.evaluation_service_v2 import evaluate_single_symbol_and_merge
        try:
            evaluate_single_symbol_and_merge(symbol=sym_upper)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Recompute failed: {e}")

    # Phase 11.2: Try exact run from history when run_id provided
    if run_id and run_id.strip():
        from app.core.eval.evaluation_store_v2 import get_decision_by_run
        artifact = get_decision_by_run(sym_upper, run_id.strip())
        if artifact is not None:
            summary = None
            for s in artifact.symbols:
                if (getattr(s, "symbol", "") or "").strip().upper() == sym_upper:
                    summary = s
                    break
            if summary is not None:
                candidates = getattr(artifact, "candidates_by_symbol", {}) or {}
                gates = getattr(artifact, "gates_by_symbol", {}) or {}
                earnings_by = getattr(artifact, "earnings_by_symbol", {}) or {}
                diag_by = getattr(artifact, "diagnostics_by_symbol", {}) or {}
                sel_c = next((c for c in (getattr(artifact, "selected_candidates", []) or []) if (getattr(c, "symbol", "") or "").strip().upper() == sym_upper), None)
                _sel_key = getattr(sel_c, "contract_key", None) if sel_c else None
                _opt_sym = getattr(sel_c, "option_symbol", None) if sel_c else None
                result = _build_symbol_diagnostics_from_v2_store(
                    summary,
                    candidates.get(sym_upper, []),
                    gates.get(sym_upper, []),
                    earnings_by.get(sym_upper),
                    diag_by.get(sym_upper),
                    sym_upper,
                    selected_contract_key=_sel_key,
                    option_symbol=_opt_sym,
                )
                result["exact_run"] = True
                result["run_id"] = (artifact.metadata or {}).get("run_id")
                return result

    from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
    store = get_evaluation_store_v2()
    store.reload_from_disk()
    row = store.get_symbol(sym_upper)
    if row is not None:
        summary, candidates, gates, earnings, diagnostics_details = row
        artifact = store.get_latest()
        sel_c = next((c for c in (getattr(artifact, "selected_candidates", []) or []) if (getattr(c, "symbol", "") or "").strip().upper() == sym_upper), None) if artifact else None
        _sel_key = getattr(sel_c, "contract_key", None) if sel_c else None
        _opt_sym = getattr(sel_c, "option_symbol", None) if sel_c else None
        out = _build_symbol_diagnostics_from_v2_store(summary, candidates, gates, earnings, diagnostics_details, sym_upper, selected_contract_key=_sel_key, option_symbol=_opt_sym)
        if run_id and run_id.strip():
            out["exact_run"] = False
            out["run_id"] = None
        return out

    # Symbol not in store — 404 (no legacy path; use recompute=1 to add symbol)
    raise HTTPException(status_code=404, detail=f"Symbol {sym_upper} not in evaluation store. Use recompute=1 to evaluate.")


@router.post("/symbols/{symbol}/recompute")
def ui_symbol_recompute(
    symbol: str = Path(..., min_length=1, max_length=12),
    force: bool = Query(False, description="Override market-closed guardrail"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Run full evaluation for one symbol and merge into the canonical store.
    Updates decision_latest.json; Universe and Dashboard read from same store.
    Phase 9: When market closed, returns 409 unless force=true.
    Returns pipeline_timestamp and updated symbol summary so UI can refetch.
    """
    _require_ui_key(x_ui_key)
    sym_upper = symbol.strip().upper()
    try:
        from app.market.market_hours import get_market_phase
        phase = get_market_phase() or "OPEN"
        if phase != "OPEN" and not force:
            raise HTTPException(
                status_code=409,
                detail="Market is closed. Refusing to overwrite canonical decision. Use force=true to override.",
            )
        if phase != "OPEN" and force:
            import logging
            logging.getLogger(__name__).info("[RECOMPUTE] Symbol %s with force=true (market phase=%s)", sym_upper, phase)
    except HTTPException:
        raise
    try:
        from app.core.eval.evaluation_service_v2 import evaluate_single_symbol_and_merge
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
        merged = evaluate_single_symbol_and_merge(symbol=sym_upper)
    except Exception as e:
        try:
            from app.api.notifications_store import append_notification
            append_notification(
                "WARN", "RECOMPUTE_FAILURE", str(e),
                symbol=sym_upper, details={"error": str(e)[:500]}, subtype="RECOMPUTE_FAILED",
            )
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
