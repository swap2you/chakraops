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


def _get_slack_status_health() -> Dict[str, Any]:
    """Phase 21.5: Slack sender status for system health. R22.2: Always return channels (signals, daily, data_health, critical) for consistent API."""
    try:
        from app.core.alerts.slack_status import get_slack_status
        return get_slack_status()
    except Exception:
        from app.core.alerts.slack_status import SLACK_CHANNELS
        empty = {"last_send_at": None, "last_send_ok": None, "last_error": None, "last_payload_type": None}
        return {
            "last_send_at": None,
            "last_send_ok": None,
            "last_error": None,
            "last_channel": None,
            "last_payload_type": None,
            "channels": {ch: dict(empty) for ch in SLACK_CHANNELS},
        }


def _get_copilot_status_health() -> Dict[str, Any]:
    """R23.4.2/R23.4.3: Copilot status for system-health (enabled, key_present, key_source, model, last_error_code). No secrets."""
    try:
        from app.api.copilot import get_copilot_status
        return get_copilot_status()
    except Exception:
        return {"enabled": False, "key_present": False, "key_format_ok": False, "key_source": "NONE", "model": "", "last_error_code": None}


def _get_mark_refresh_health() -> Dict[str, Any]:
    """Phase 16.0: Mark refresh state for system health."""
    try:
        from app.core.portfolio.mark_refresh_state import load_mark_refresh_state
        state = load_mark_refresh_state()
        if state is None:
            return {"last_run_at_utc": None, "last_result": None, "updated_count": None, "skipped_count": None, "error_count": None, "errors_sample": []}
        return {
            "last_run_at_utc": state.get("last_run_at_utc"),
            "last_result": state.get("last_result"),
            "updated_count": state.get("updated_count"),
            "skipped_count": state.get("skipped_count"),
            "error_count": state.get("error_count"),
            "errors_sample": state.get("errors_sample") or [],
        }
    except Exception:
        return {"last_run_at_utc": None, "last_result": None, "updated_count": None, "skipped_count": None, "error_count": None, "errors_sample": []}


def _get_portfolio_risk_notifier_health() -> Dict[str, Any]:
    """R24.3.1: Portfolio risk notifier for system health — safe status/label only (OK/Degraded/Advisory)."""
    try:
        from app.core.portfolio.risk_notify_state import get_portfolio_risk_notifier_display
        return get_portfolio_risk_notifier_display()
    except Exception:
        return {"status": "OK", "label": "OK"}


def _get_guardrails_health() -> Dict[str, Any]:
    """R25.9: Guardrails block for system health — status (OK/Advisory/Blocked), metrics, limits. Safe labels only."""
    try:
        from app.core.portfolio.guardrails_r259 import get_guardrails_metrics_and_status
        return get_guardrails_metrics_and_status()
    except Exception:
        return {
            "status": "OK",
            "metrics": {"cash_reserve_pct": 0, "open_options_count": 0, "open_shares_count": 0, "symbols_exposure_count": 0, "max_symbol_notional_pct": 0},
            "limits": {},
        }


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


def _build_universe_symbols_list(artifact: Any) -> List[Dict[str, Any]]:
    """Build the symbols list for universe response. Used by ui_universe and get_universe_row_for_copilot.
    R23.4.5: When diagnostics missing, use same request-time technicals + mtf_levels as symbol-diagnostics
    so shares_eligible matches Shares tab (compute_shares_eligibility with same inputs)."""
    symbols_out: List[Dict[str, Any]] = []
    if not artifact:
        return symbols_out
    sel_by_sym: Dict[str, Any] = {}
    for c in getattr(artifact, "selected_candidates", []) or []:
        sym_k = (getattr(c, "symbol", "") or "").strip().upper()
        if sym_k:
            sel_by_sym[sym_k] = c
    diag_by_sym = getattr(artifact, "diagnostics_by_symbol", None) or {}
    pipeline_ts = (getattr(artifact, "metadata", None) or {}).get("pipeline_timestamp") if artifact else None
    for s in getattr(artifact, "symbols", []) or []:
        sym_key = (s.symbol or "").strip().upper()
        diag = diag_by_sym.get(sym_key)
        diag_dict = diag.to_dict() if diag and hasattr(diag, "to_dict") else (diag if isinstance(diag, dict) else {})
        sel_el = (diag_dict.get("symbol_eligibility") or getattr(diag, "symbol_eligibility", None) or {}) if diag else {}
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
            "primary_reason": _primary_reason_display(s),
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
        try:
            from app.core.shares.shares_plan import compute_shares_eligibility
            tech = (diag_dict.get("technicals") if diag_dict else (getattr(diag, "technicals", None) if diag else None)) or {}
            mtf_levels = None
            if not tech and sym_key:
                spot_u = float(getattr(s, "price", None) or getattr(s, "underlying_price", None) or 0)
                tech = _build_technicals_at_request_time(sym_key, spot_u if spot_u > 0 else None)
            if sym_key and tech:
                mtf_levels = _build_mtf_levels_at_request_time(sym_key, tech, {}, pipeline_ts)
            shares_eligible, _ = compute_shares_eligibility(s, tech, sel_el, mtf_levels=mtf_levels, symbol=sym_key)
            row["shares_eligible"] = shares_eligible
        except Exception:
            row["shares_eligible"] = False
        sample = (getattr(diag, "sample_rejected_due_to_delta", None) or (diag.get("sample_rejected_due_to_delta") if isinstance(diag, dict) else None) or []) if diag else []
        row["reasons_explained"] = _compute_reasons_explained(
            getattr(s, "primary_reason", None) or "",
            sel_el,
            sample,
        )
        sel_cand = sel_by_sym.get(sym_key)
        if sel_cand and (s.verdict or "").upper() == "ELIGIBLE":
            row["selected_contract_key"] = getattr(sel_cand, "contract_key", None)
            row["option_symbol"] = getattr(sel_cand, "option_symbol", None)
            row["strike"] = getattr(sel_cand, "strike", None)
        symbols_out.append(row)
    return symbols_out


def get_universe_row_for_copilot(symbol: str) -> Optional[Dict[str, Any]]:
    """R23.4: Return single universe row for symbol (for copilot tools). No auth. Returns None if not found."""
    sym_upper = (symbol or "").strip().upper()
    if not sym_upper:
        return None
    from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
    store = get_evaluation_store_v2()
    store.reload_from_disk()
    artifact = store.get_latest()
    if not artifact:
        return None
    symbols_out = _build_universe_symbols_list(artifact)
    for r in symbols_out:
        if (r.get("symbol") or "").strip().upper() == sym_upper:
            return r
    return None


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
        symbols_out = _build_universe_symbols_list(artifact)
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


# ---------------------------------------------------------------------------
# Phase 21.3: Universe overlay — add/remove symbols (GET/POST/DELETE /api/ui/universe/symbols)
# ---------------------------------------------------------------------------


@router.get("/universe/symbols")
def ui_universe_symbols(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Effective universe list and overlay counts: base_count, overlay_added_count, overlay_removed_count, symbols.
    Single source of truth for evaluation and Universe Manager UI.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.api.data_health import get_base_universe_symbols
        from app.core.universe.universe_overrides import get_effective_symbols, get_overlay_counts
        base = get_base_universe_symbols()
        symbols = get_effective_symbols(base)
        added_count, removed_count = get_overlay_counts()
        return {
            "base_count": len(base),
            "overlay_added_count": added_count,
            "overlay_removed_count": removed_count,
            "symbols": symbols,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading universe symbols: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/universe/symbols")
async def ui_universe_symbols_add(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Add symbol to overlay (add to added, remove from removed if present). Body: { symbol }."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.universe.universe_overrides import add_symbol, get_effective_symbols
        from app.api.data_health import get_base_universe_symbols
        body = await request.json()
        symbol = (body.get("symbol") or "").strip()
        ok, err = add_symbol(symbol)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Invalid symbol")
        base = get_base_universe_symbols()
        effective = get_effective_symbols(base)
        return {"symbol": symbol.upper(), "symbols": effective}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error adding universe symbol: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/universe/symbols/{symbol}")
def ui_universe_symbols_remove(
    symbol: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Remove symbol (add to overlay.removed, remove from overlay.added if present)."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.universe.universe_overrides import remove_symbol, get_effective_symbols
        from app.api.data_health import get_base_universe_symbols
        ok, err = remove_symbol(symbol)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Invalid symbol")
        base = get_base_universe_symbols()
        effective = get_effective_symbols(base)
        return {"removed": symbol.strip().upper(), "symbols": effective}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error removing universe symbol: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/universe/reset")
def ui_universe_reset(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Clear overlay (added and removed). Admin / Universe Manager."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.universe.universe_overrides import reset_overlay, get_effective_symbols
        from app.api.data_health import get_base_universe_symbols
        reset_overlay()
        base = get_base_universe_symbols()
        effective = get_effective_symbols(base)
        return {"reset": True, "symbols": effective}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error resetting universe overlay: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# R25.6: Universe Admin (propose/apply, audit log) + Universe Health
# ---------------------------------------------------------------------------

@router.get("/universe/admin")
def ui_universe_admin(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.6: Current universe list + recent change history."""
    _require_ui_key(x_ui_key)
    try:
        from app.api.data_health import get_base_universe_symbols
        from app.core.universe.universe_overrides import get_effective_symbols, get_overlay_counts
        from app.core.universe.universe_admin_store import list_history
        base = get_base_universe_symbols()
        symbols = get_effective_symbols(base)
        added_count, removed_count = get_overlay_counts()
        history = list_history(limit=limit, offset=offset, status=(status or "").strip() or None)
        return {
            "symbols": symbols,
            "base_count": len(base),
            "overlay_added_count": added_count,
            "overlay_removed_count": removed_count,
            "history": history,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Universe admin list error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to load universe admin data")


@router.post("/universe/propose-add")
async def ui_universe_propose_add(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.6: Propose adding a symbol. Body: symbol, reason_code?, notes?."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    symbol = (body.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    reason_code = (body.get("reason_code") or "").strip() or None
    notes = (body.get("notes") or "").strip()[:1000] or None
    try:
        from app.core.universe.universe_admin_store import create_proposal
        from app.core.universe.universe_overrides import validate_symbol
        ok, err = validate_symbol(symbol)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Invalid symbol")
        record = create_proposal("PROPOSE_ADD", symbol, reason_code=reason_code, notes=notes)
        return {"proposal": record}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Propose add error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to create proposal")


@router.post("/universe/propose-remove")
async def ui_universe_propose_remove(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.6: Propose removing a symbol. Body: symbol, reason_code?, notes?."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    symbol = (body.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    reason_code = (body.get("reason_code") or "").strip() or None
    notes = (body.get("notes") or "").strip()[:1000] or None
    try:
        from app.core.universe.universe_admin_store import create_proposal
        record = create_proposal("PROPOSE_REMOVE", symbol, reason_code=reason_code, notes=notes)
        return {"proposal": record}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Propose remove error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to create proposal")


@router.post("/universe/apply")
async def ui_universe_apply(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.6: Apply add or remove. Body: proposal_id (to apply proposal) or symbol + action (add|remove)."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    proposal_id = (body.get("proposal_id") or "").strip() or None
    symbol = (body.get("symbol") or "").strip().upper()
    action = (body.get("action") or "").strip().lower()

    if proposal_id:
        from app.core.universe.universe_admin_store import get_proposal, mark_applied
        from app.core.universe.universe_overrides import add_symbol, remove_symbol, get_effective_symbols
        from app.api.data_health import get_base_universe_symbols
        prop = get_proposal(proposal_id)
        if not prop or prop.get("status") != "OPEN":
            raise HTTPException(status_code=404, detail="Proposal not found or already applied")
        sym = (prop.get("symbol") or "").strip().upper()
        act = prop.get("action", "")
        if act == "PROPOSE_ADD":
            ok, err = add_symbol(sym)
            if not ok:
                raise HTTPException(status_code=400, detail=err or "Invalid symbol")
            mark_applied(proposal_id)
            from app.core.universe.universe_admin_store import log_apply
            log_apply("APPLY_ADD", sym, prop.get("reason_code"), prop.get("notes"))
        elif act == "PROPOSE_REMOVE":
            ok, err = remove_symbol(sym)
            if not ok:
                raise HTTPException(status_code=400, detail=err or "Invalid symbol")
            mark_applied(proposal_id)
            from app.core.universe.universe_admin_store import log_apply
            log_apply("APPLY_REMOVE", sym, prop.get("reason_code"), prop.get("notes"))
        else:
            raise HTTPException(status_code=400, detail="Unsupported proposal action")
        base = get_base_universe_symbols()
        effective = get_effective_symbols(base)
        return {"applied": True, "symbol": sym, "action": act.replace("PROPOSE_", "APPLY_"), "symbols": effective}
    if symbol and action in ("add", "remove"):
        from app.core.universe.universe_overrides import add_symbol, remove_symbol, get_effective_symbols
        from app.api.data_health import get_base_universe_symbols
        from app.core.universe.universe_admin_store import log_apply
        if action == "add":
            ok, err = add_symbol(symbol)
            if not ok:
                raise HTTPException(status_code=400, detail=err or "Invalid symbol")
            log_apply("APPLY_ADD", symbol)
        else:
            ok, err = remove_symbol(symbol)
            if not ok:
                raise HTTPException(status_code=400, detail=err or "Invalid symbol")
            log_apply("APPLY_REMOVE", symbol)
        base = get_base_universe_symbols()
        effective = get_effective_symbols(base)
        return {"applied": True, "symbol": symbol, "action": f"APPLY_{action.upper()}", "symbols": effective}
    raise HTTPException(status_code=400, detail="Provide proposal_id or symbol and action (add|remove)")


@router.get("/universe/health")
def ui_universe_health(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.6: Universe health summary: total, recently added/removed, warnings count (safe labels)."""
    _require_ui_key(x_ui_key)
    try:
        from app.api.data_health import get_base_universe_symbols
        from app.core.universe.universe_overrides import get_effective_symbols
        from app.core.universe.universe_admin_store import recent_changes_days
        base = get_base_universe_symbols()
        symbols = get_effective_symbols(base)
        added_30, removed_30 = recent_changes_days(30)
        # Warnings: data unavailable count (placeholder; can hook into data health later)
        warnings_count = 0
        earnings_upcoming = None  # Optional: hook into earnings advisory when available
        return {
            "total_symbols": len(symbols),
            "base_count": len(base),
            "recently_added": added_30[:20],
            "recently_removed": removed_30[:20],
            "warnings_count": warnings_count,
            "earnings_upcoming": earnings_upcoming,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Universe health error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to load universe health")


# R25.8: Earnings feed validation — diagnostics only; safe fields; no raw ORATS; no persist
@router.get("/earnings/debug")
def ui_earnings_debug(
    symbol: str = Query(..., description="Ticker to probe (e.g. NVDA, SPY)"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Diagnostics-only endpoint. Returns safe fields: status, next_date, days, implied_move_pct, as_of.
    Does not return raw ORATS payload; does not log secrets; does not persist to decision artifacts.
    """
    _require_ui_key(x_ui_key)
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"status": "Unavailable", "next_date": None, "days": None, "implied_move_pct": None, "as_of": None}
    try:
        from app.core.config.orats_secrets import ORATS_API_TOKEN
        from app.core.orats.earnings import fetch_earnings_advisory
        token = (ORATS_API_TOKEN or "").strip() or None
        out = fetch_earnings_advisory(sym, token=token)
        # Map to safe field names only; never raw codes
        status = (out.get("earnings_data_status") or "Unavailable").strip()
        if status not in ("OK", "Unavailable", "Stale"):
            status = "Unavailable"
        return {
            "status": status,
            "next_date": out.get("earnings_next_date"),
            "days": out.get("earnings_days"),
            "implied_move_pct": out.get("implied_earnings_move_pct"),
            "as_of": out.get("earnings_as_of"),
        }
    except Exception:
        return {"status": "Unavailable", "next_date": None, "days": None, "implied_move_pct": None, "as_of": None}


# R23.2: Delta band overrides (advanced) — chakraops/data/delta_overrides.json; NOT in out/
@router.get("/delta-overrides")
def ui_delta_overrides_list(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """List per-symbol delta band overrides. Advanced."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.config.delta_overrides import load_delta_overrides
        overrides = load_delta_overrides()
        return {"overrides": dict(overrides)}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading delta overrides: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delta-overrides/{symbol}")
async def ui_delta_overrides_set(
    symbol: str,
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Set delta band override for symbol. Enforces DELTA_OVERRIDE_MAX_WIDEN. Body: { delta_lo, delta_hi }."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
        delta_lo = body.get("delta_lo")
        delta_hi = body.get("delta_hi")
        if delta_lo is None or delta_hi is None:
            raise HTTPException(status_code=400, detail="delta_lo and delta_hi required")
        try:
            delta_lo = float(delta_lo)
            delta_hi = float(delta_hi)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="delta_lo and delta_hi must be numbers")
        from app.core.config.delta_overrides import save_delta_override
        from app.core.config.trade_rules import CSP_TARGET_DELTA_LOW, CSP_TARGET_DELTA_HIGH, DELTA_OVERRIDE_MAX_WIDEN
        canonical_lo = float(CSP_TARGET_DELTA_LOW)
        canonical_hi = float(CSP_TARGET_DELTA_HIGH)
        max_widen = float(DELTA_OVERRIDE_MAX_WIDEN)
        ok, err = save_delta_override(
            symbol.strip().upper(), delta_lo, delta_hi, max_widen, canonical_lo, canonical_hi
        )
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Invalid override")
        return {"symbol": symbol.strip().upper(), "delta_lo": delta_lo, "delta_hi": delta_hi}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error saving delta override: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delta-overrides/{symbol}")
def ui_delta_overrides_delete(
    symbol: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Remove delta band override for symbol."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.config.delta_overrides import delete_delta_override
        ok = delete_delta_override(symbol.strip().upper())
        if not ok:
            raise HTTPException(status_code=400, detail="Failed to delete override")
        return {"symbol": symbol.strip().upper(), "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error deleting delta override: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/admin/slack/test")
def ui_admin_slack_test(
    channel: str = Query(default="signals", description="Channel: signals | daily | data_health | critical"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 21.5 / R21.5.1: Send a test Slack message to the given channel and update that channel's status.
    Guarded by UI key. Response includes channel, ok, message, updated_status (full slack status).
    """
    _require_ui_key(x_ui_key)
    import logging
    log = logging.getLogger(__name__)
    from app.core.alerts.slack_status import SLACK_CHANNELS, get_slack_status, update_slack_status
    ch = (channel or "signals").strip().lower()
    if ch not in SLACK_CHANNELS:
        ch = "signals"
    try:
        from app.core.alerts.slack_dispatcher import get_webhook_for_channel, send_slack_message
        webhook = get_webhook_for_channel(ch)
        if not webhook:
            update_slack_status(ch, ok=False, error="no_webhook", payload_type="test")
            return {
                "status": "error",
                "channel": ch,
                "message": "Slack not configured for channel",
                "ok": False,
                "updated_status": get_slack_status(),
            }
        text = f"ChakraOps R21.5.1 test — {ch} channel"
        ok = send_slack_message(webhook, text)
        update_slack_status(ch, ok=ok, error=None if ok else "send_failed", payload_type="test")
        return {
            "status": "OK",
            "channel": ch,
            "message": "Test message sent" if ok else "Send failed",
            "ok": ok,
            "updated_status": get_slack_status(),
        }
    except Exception as e:
        log.exception("Slack test failed: %s", e)
        try:
            update_slack_status(ch, ok=False, error=str(e), payload_type="test")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/evaluation/force")
def ui_admin_evaluation_force(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 21.5: Run one evaluation cycle immediately (force). Bypasses scheduler market check.
    Safe: runs same trigger_evaluation as scheduler; logs that it was forced.
    """
    _require_ui_key(x_ui_key)
    import logging
    log = logging.getLogger(__name__)
    try:
        from app.api.data_health import get_universe_symbols
        from app.core.eval.universe_evaluator import trigger_evaluation
        from app.market.market_hours import get_market_phase
        symbols = list(get_universe_symbols())
        if not symbols:
            return {
                "status": "OK",
                "started": False,
                "reason": "no_symbols",
                "forced": True,
                "message": "Universe empty; nothing to run",
            }
        phase = get_market_phase() or "UNKNOWN"
        log.info("[ADMIN] Force evaluation requested (market_phase=%s)", phase)
        result = trigger_evaluation(symbols, market_phase=phase)
        started = result.get("started", False)
        return {
            "status": "OK",
            "started": started,
            "run_id": result.get("run_id"),
            "reason": result.get("reason"),
            "forced": True,
        }
    except Exception as e:
        log.exception("Force evaluation failed: %s", e)
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

    # ORATS: data health (Phase 9: age_minutes, staleness_threshold). R22.2: orats_freshness_state OK/DELAYED/WARN/ERROR.
    orats_status = "UNKNOWN"
    orats_last_success: str | None = None
    orats_avg_latency: float | None = None
    orats_last_error: str | None = None
    orats_age_minutes: float | None = None
    orats_staleness_minutes: int = 30
    orats_freshness_state: str = "UNKNOWN"
    orats_freshness_state_label: str | None = None
    orats_as_of: str | None = None
    orats_threshold_triggered: str | None = None
    try:
        from app.api.data_health import get_data_health, get_orats_freshness_state
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
        freshness = get_orats_freshness_state()
        orats_freshness_state = freshness.get("state") or "UNKNOWN"
        orats_freshness_state_label = freshness.get("state_label")
        orats_as_of = freshness.get("as_of")
        orats_threshold_triggered = freshness.get("threshold_triggered")
    except Exception:
        orats_status = "DOWN"
        orats_last_error = "Failed to read data health"
        orats_freshness_state = "ERROR"
        orats_freshness_state_label = "ERROR"
        orats_as_of = None
        orats_threshold_triggered = "error"

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

    # Scheduler: interval, heartbeat (last_run_at, next_run_at, last_result, last_skip_reason; R21.5.1: duration, run_ok, error, run_count_today)
    scheduler_interval: int | None = None
    scheduler_nightly_next: str | None = None
    scheduler_eod_next: str | None = None
    scheduler_last_run_at: str | None = None
    scheduler_next_run_at: str | None = None
    scheduler_last_result: str | None = None
    scheduler_last_skip_reason: str | None = None
    scheduler_last_duration_ms: float | None = None
    scheduler_last_run_ok: bool | None = None
    scheduler_last_run_error: str | None = None
    scheduler_run_count_today: int | None = None
    try:
        from app.api.server import get_scheduler_status, get_nightly_scheduler_status
        sched = get_scheduler_status()
        scheduler_interval = sched.get("interval_minutes")
        scheduler_last_run_at = sched.get("last_run_at")
        scheduler_next_run_at = sched.get("next_run_at")
        scheduler_last_result = sched.get("last_result")
        scheduler_last_skip_reason = sched.get("last_skip_reason")
        scheduler_last_duration_ms = sched.get("last_duration_ms")
        scheduler_last_run_ok = sched.get("last_run_ok")
        scheduler_last_run_error = sched.get("last_run_error")
        scheduler_run_count_today = sched.get("run_count_today")
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

    # R25.4: Notifications health (counts, last emitted; safe labels only)
    notifications_health: Dict[str, Any] = {}
    try:
        from app.api.notifications_store import get_notifications_health
        notifications_health = get_notifications_health()
    except Exception:
        notifications_health = {"count_new": 0, "count_acked": 0, "count_archived": 0, "last_emitted_ts": None}

    # R25.8: Cadence for banner (safe labels only)
    cadence_mode_health = "EOD_BIASED"
    eligibility_as_of_health: str | None = decision_eval_ts
    try:
        from app.core.settings import get_decision_cadence_mode
        cadence_mode_health = get_decision_cadence_mode()
    except Exception:
        pass
    # R25.8: Earnings probe symbol (default SPY) for System Diagnostics card
    earnings_probe_symbol = (__import__("os").environ.get("EARNINGS_PROBE_SYMBOL") or "SPY").strip().upper() or "SPY"

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
            "orats_freshness_state": orats_freshness_state,
            "orats_freshness_state_label": orats_freshness_state_label,
            "orats_as_of": orats_as_of,
            "orats_threshold_triggered": orats_threshold_triggered,
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
            "last_skip_reason": scheduler_last_skip_reason,
            "last_duration_ms": scheduler_last_duration_ms,
            "last_run_ok": scheduler_last_run_ok,
            "last_run_error": scheduler_last_run_error,
            "run_count_today": scheduler_run_count_today,
        },
        "slack": _get_slack_status_health(),
        "eod_freeze": _get_eod_freeze_health(),
        "mark_refresh": _get_mark_refresh_health(),
        "copilot": _get_copilot_status_health(),
        "portfolio_risk_notifier": _get_portfolio_risk_notifier_health(),
        "notifications": notifications_health,
        "cadence": {"mode": cadence_mode_health, "eligibility_as_of": eligibility_as_of_health},
        "earnings_probe_symbol": earnings_probe_symbol,
        "guardrails": _get_guardrails_health(),
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


@router.get("/stores/integrity")
def ui_stores_integrity(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 17.0: Scan key JSONL stores for integrity. Returns scan results per store."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.io.jsonl_integrity import get_store_paths, scan_jsonl
        store_paths = get_store_paths()
        results: Dict[str, Any] = {}
        for name, path in store_paths.items():
            results[name] = scan_jsonl(path)
        return {"stores": results}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error scanning stores: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stores/repair")
def ui_stores_repair(
    store: str = Query(..., description="Store name: notifications, diagnostics_history, positions_events"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 17.0: Repair a JSONL store — remove invalid lines, save backup. Returns before/after counts."""
    _require_ui_key(x_ui_key)
    from app.core.io.jsonl_integrity import get_store_paths
    store_paths = get_store_paths()
    if store not in store_paths:
        raise HTTPException(status_code=400, detail=f"Unknown store: {store}. Use: {list(store_paths.keys())}")
    try:
        from app.core.io.jsonl_integrity import scan_jsonl, repair_jsonl
        path = store_paths[store]
        before = scan_jsonl(path)
        repair_result = repair_jsonl(path)
        after = scan_jsonl(path)
        return {
            "store": store,
            "before": {"total_lines": before["total_lines"], "invalid_lines": before["invalid_lines"]},
            "after": {"valid_count": repair_result["valid_count"], "removed_count": repair_result["removed_count"]},
            "backup_path": repair_result.get("backup_path"),
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error repairing store %s: %s", store, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decisions/archive/prune")
def ui_decisions_archive_prune(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Prune decision archive (out/decisions/<symbol>/*.json) to at most DECISION_ARCHIVE_MAX per symbol. Safe to call repeatedly."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.eval.evaluation_store_v2 import prune_decision_archives
        return prune_decision_archives()
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error pruning decision archives: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
    state: str | None = Query(default=None, description="Filter by state: NEW, ACKED, ARCHIVED"),
    symbol: str | None = Query(default=None, description="Filter by symbol (case-insensitive)"),
    type_filter: str | None = Query(default=None, alias="type", description="Filter by notification type"),
    offset: int = Query(default=0, ge=0, le=10000),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Return notifications (newest first). R25.4: state, symbol, type, limit, offset; each item has created_ts, acked_ts, archived_ts."""
    _require_ui_key(x_ui_key)
    try:
        from app.api.notifications_store import load_notifications
        state_filter = state.strip() if state and state.strip() else None
        if state_filter and state_filter not in ("NEW", "ACKED", "ARCHIVED"):
            state_filter = None
        items = load_notifications(
            limit=limit,
            state_filter=state_filter,
            symbol_filter=symbol.strip() if symbol and symbol.strip() else None,
            type_filter=type_filter.strip() if type_filter and type_filter.strip() else None,
            offset=offset,
        )
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


@router.post("/notifications/archive_all")
def ui_notifications_archive_all(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 21.5: Archive all NEW/ACKED notifications. Returns count archived."""
    _require_ui_key(x_ui_key)
    try:
        from app.api.notifications_store import archive_all
        count = archive_all()
        return {"status": "OK", "archived_count": count}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error archiving all notifications: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/ack-bulk")
def ui_notifications_ack_bulk(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.4: Ack all NEW notifications. Returns count acked."""
    _require_ui_key(x_ui_key)
    try:
        from app.api.notifications_store import ack_bulk
        count = ack_bulk(state_filter="NEW")
        return {"status": "OK", "acked_count": count}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error acking notifications: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notifications/archive-bulk")
def ui_notifications_archive_bulk(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.4: Archive all ACKED notifications. Returns count archived."""
    _require_ui_key(x_ui_key)
    try:
        from app.api.notifications_store import archive_bulk
        count = archive_bulk(state_filter="ACKED")
        return {"status": "OK", "archived_count": count}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error archiving notifications: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/notifications/{notification_id}/archive")
def ui_notification_archive(
    notification_id: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 21.5: Archive a notification (append state event)."""
    _require_ui_key(x_ui_key)
    if not notification_id or not notification_id.strip():
        raise HTTPException(status_code=400, detail="notification_id required")
    try:
        from app.api.notifications_store import append_archive
        append_archive(notification_id.strip())
        return {"status": "OK", "updated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error archiving notification: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notifications/{notification_id}")
def ui_notification_delete(
    notification_id: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 21.5: Soft-delete a notification (append DELETED state event). Removed from default list."""
    _require_ui_key(x_ui_key)
    if not notification_id or not notification_id.strip():
        raise HTTPException(status_code=400, detail="notification_id required")
    try:
        from app.api.notifications_store import append_delete
        append_delete(notification_id.strip())
        return {"status": "OK", "updated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error deleting notification: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# R26.2: Trade Ticket v2 — GET ticket payload; POST journal from ticket
# ---------------------------------------------------------------------------


@router.get("/trade-ticket")
def ui_trade_ticket(
    symbol: str = Query(..., description="Symbol"),
    strategy: str = Query("SHARES", description="SHARES | CSP | CC"),
    action: str = Query("OPEN", description="OPEN | CLOSE | BUY | SELL"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.2: Build trade ticket (snapshot/sizing/contract/steps/journal draft). No decision persistence."""
    _require_ui_key(x_ui_key)
    from app.core.portfolio.trade_ticket_r262 import build_trade_ticket
    ticket = build_trade_ticket(symbol=symbol, strategy=strategy, action=action)
    return ticket


@router.post("/journal/from-ticket")
async def ui_journal_from_ticket(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.2: Create journal entry from ticket payload (same schema as POST /journal)."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    trade_date = (body.get("trade_date") or "").strip()[:10]
    symbol = (body.get("symbol") or "").strip().upper()
    strategy = (body.get("strategy") or "SHARES").strip().upper()
    action = (body.get("action") or "").strip().upper()
    if not trade_date or not symbol or not action:
        raise HTTPException(status_code=400, detail="trade_date, symbol, and action required")
    try:
        qty = float(body.get("qty", 0))
    except (TypeError, ValueError):
        qty = 0.0
    price = body.get("price")
    premium = body.get("premium")
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None
    if premium is not None:
        try:
            premium = float(premium)
        except (TypeError, ValueError):
            premium = None
    fees = body.get("fees")
    if fees is not None:
        try:
            fees = float(fees)
        except (TypeError, ValueError):
            fees = None
    strike_val = None
    if body.get("strike") is not None:
        try:
            strike_val = float(body["strike"])
        except (TypeError, ValueError):
            pass
    realized_val = None
    if body.get("realized_pl") is not None:
        try:
            realized_val = float(body["realized_pl"])
        except (TypeError, ValueError):
            pass
    try:
        from app.core.journal.journal_store import journal_create
        entry = journal_create(
            trade_date=trade_date,
            symbol=symbol,
            strategy=strategy,
            action=action,
            qty=qty,
            price=price,
            premium=premium,
            fees=fees,
            contract_key=(body.get("contract_key") or "").strip() or None,
            expiry=(body.get("expiry") or "").strip()[:10] or None,
            strike=strike_val,
            right=(body.get("right") or "").strip() or None,
            notes=(body.get("notes") or "").strip()[:2000] or None,
            tags=(body.get("tags") or "").strip()[:500] or None,
            realized_pl=realized_val,
            link_id=(body.get("link_id") or "").strip() or None,
        )
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Journal from-ticket error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to create entry")


# ---------------------------------------------------------------------------
# R26.3: Today summary — lightweight single payload for Today page
# ---------------------------------------------------------------------------


def _format_ts_et(ts_utc: str | None) -> str:
    """Format UTC timestamp to ET display string for Today summary."""
    if not ts_utc or not isinstance(ts_utc, str):
        return "—"
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        et = dt.astimezone(ZoneInfo("America/New_York"))
        return et.strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        return str(ts_utc)[:19] + " ET"


@router.get("/today/summary")
def ui_today_summary(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.3: Lightweight summary for Today page. Same as_of as decision store; no heavy ORATS."""
    _require_ui_key(x_ui_key)
    latest_run_ts: str | None = None
    as_of_et = "—"
    try:
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2, get_eval_snapshot
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        artifact = store.get_latest()
        if artifact and getattr(artifact, "metadata", None):
            latest_run_ts = (artifact.metadata or {}).get("pipeline_timestamp")
        if not latest_run_ts:
            snap = get_eval_snapshot()
            if isinstance(snap, dict):
                latest_run_ts = snap.get("quote_as_of") or snap.get("pipeline_timestamp")
        as_of_et = _format_ts_et(latest_run_ts)
    except Exception:
        pass

    cadence_mode = "EOD_BIASED"
    eligibility_as_of: str | None = latest_run_ts
    try:
        from app.core.settings import get_decision_cadence_mode
        cadence_mode = get_decision_cadence_mode()
    except Exception:
        pass

    guardrails = _get_guardrails_health()

    orats_status = "UNKNOWN"
    orats_freshness_state_label: str | None = None
    try:
        from app.api.data_health import get_data_health, get_orats_freshness_state
        dh = get_data_health()
        raw = (dh.get("status") or "UNKNOWN").upper()
        if raw == "OK":
            orats_status = "OK"
        elif raw in ("WARN", "DEGRADED"):
            orats_status = "WARN"
        else:
            orats_status = "DOWN"
        freshness = get_orats_freshness_state()
        orats_freshness_state_label = freshness.get("state_label") or freshness.get("state")
    except Exception:
        orats_status = "DOWN"

    notifications_health: Dict[str, Any] = {}
    notifications_new_count = 0
    try:
        from app.api.notifications_store import get_notifications_health
        notifications_health = get_notifications_health()
        notifications_new_count = int(notifications_health.get("count_new") or 0)
    except Exception:
        notifications_health = {"count_new": 0, "count_acked": 0, "count_archived": 0, "last_emitted_ts": None}

    earnings_probe: Dict[str, Any] = {"status": "Unavailable", "next_date": None, "days": None, "implied_move_pct": None, "as_of": None}
    try:
        import os
        sym = (os.environ.get("EARNINGS_PROBE_SYMBOL") or "SPY").strip().upper() or "SPY"
        from app.core.orats.earnings import fetch_earnings_advisory
        from app.core.config.orats_secrets import ORATS_API_TOKEN
        token = (ORATS_API_TOKEN or "").strip() or None
        out = fetch_earnings_advisory(sym, token=token)
        status = (out.get("earnings_data_status") or "Unavailable").strip()
        if status not in ("OK", "Unavailable", "Stale"):
            status = "Unavailable"
        earnings_probe = {
            "status": status,
            "next_date": out.get("earnings_next_date"),
            "days": out.get("earnings_days"),
            "implied_move_pct": out.get("implied_earnings_move_pct"),
            "as_of": out.get("earnings_as_of"),
        }
    except Exception:
        pass

    # action_needed_count: client should derive from GET /api/ui/action-needed to avoid duplicate heavy work
    action_needed_count: int | None = None

    return {
        "latest_run_ts": latest_run_ts,
        "as_of_et": as_of_et,
        "cadence": {"mode": cadence_mode, "eligibility_as_of": eligibility_as_of},
        "orats_status": orats_status,
        "orats_freshness_state_label": orats_freshness_state_label,
        "guardrails": guardrails,
        "notifications_health": notifications_health,
        "notifications_new_count": notifications_new_count,
        "earnings_probe": earnings_probe,
        "action_needed_count": action_needed_count,
    }


# ---------------------------------------------------------------------------
# R26.4: Ops checklists (EOD / Weekly) + eod-summary / weekly-summary
# ---------------------------------------------------------------------------


@router.get("/ops/checklist")
def ui_ops_checklist(
    kind: str = Query(..., description="EOD or WEEKLY"),
    key: str = Query(..., description="YYYY-MM-DD for EOD, YYYY-WW for WEEKLY"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.4: Get checklist state for kind+key."""
    _require_ui_key(x_ui_key)
    from app.core.ops.checklist_store_r264 import checklist_get, checklist_ensure_open, KIND_EOD, KIND_WEEKLY
    k = (kind or "").strip().upper()
    key_val = (key or "").strip()
    if k not in (KIND_EOD, KIND_WEEKLY):
        raise HTTPException(status_code=400, detail="kind must be EOD or WEEKLY")
    if not key_val:
        raise HTTPException(status_code=400, detail="key required")
    row = checklist_get(k, key_val)
    if row is None:
        row = checklist_ensure_open(k, key_val)
    return {"kind": k, "key": key_val, "row": row}


@router.post("/ops/checklist/mark-done")
async def ui_ops_checklist_mark_done(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.4: Mark checklist DONE for kind+key. Body: kind, key, notes?, override_reason? (R26.9: required when EOD and NEW notifications)."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    kind = (body.get("kind") or "").strip().upper()
    key_val = (body.get("key") or "").strip()
    notes = (body.get("notes") or "").strip()[:2000] or None
    override_reason = (body.get("override_reason") or "").strip()[:140] or None
    from app.core.ops.checklist_store_r264 import checklist_set_done, KIND_EOD, KIND_WEEKLY
    if kind not in (KIND_EOD, KIND_WEEKLY):
        raise HTTPException(status_code=400, detail="kind must be EOD or WEEKLY")
    if not key_val:
        raise HTTPException(status_code=400, detail="key required")
    # R26.9: EOD mark-done blocked when NEW notifications exist unless override_reason provided
    if kind == KIND_EOD:
        from app.api.notifications_store import get_notifications_health
        from app.core.ops.execution_log_store_r269 import execution_log_append, EVENT_EOD_OVERRIDE
        health = get_notifications_health()
        count_new = int(health.get("count_new") or 0)
        if count_new > 0 and not override_reason:
            raise HTTPException(
                status_code=409,
                detail="Cannot complete EOD while inbox has NEW items.",
            )
        if count_new > 0 and override_reason:
            execution_log_append(EVENT_EOD_OVERRIDE, reason=override_reason)
    row = checklist_set_done(kind, key_val, notes=notes)
    return {"status": "OK", "row": row}


# ---------------------------------------------------------------------------
# R26.9: Ops execution log (overrides and done transitions)
# ---------------------------------------------------------------------------


@router.post("/ops/execution-log")
async def ui_ops_execution_log_post(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.9: Write one execution log event. Body: event_type, symbol?, strategy?, action?, ticket_id?, reason?. No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    event_type = (body.get("event_type") or "").strip().upper()
    symbol = (body.get("symbol") or "").strip() or None
    strategy = (body.get("strategy") or "").strip() or None
    action = (body.get("action") or "").strip() or None
    ticket_id = (body.get("ticket_id") or "").strip() or None
    reason = (body.get("reason") or "").strip()[:140] or None
    from app.core.ops.execution_log_store_r269 import execution_log_append, VALID_EVENTS
    if event_type not in VALID_EVENTS:
        raise HTTPException(status_code=400, detail=f"event_type must be one of {list(VALID_EVENTS)}")
    row = execution_log_append(event_type=event_type, symbol=symbol, strategy=strategy, action=action, ticket_id=ticket_id, reason=reason)
    return {"status": "OK", "row": row}


@router.get("/ops/execution-log")
def ui_ops_execution_log_get(
    date: str | None = Query(None, description="YYYY-MM-DD (optional)"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.9: List execution log rows. Optional date filter. No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    from app.core.ops.execution_log_store_r269 import execution_log_list
    date_str = (date or "").strip()[:10] if date else None
    if date_str and (len(date_str) != 10 or date_str[4] != "-" or date_str[7] != "-"):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    rows = execution_log_list(date=date_str)
    return {"rows": rows}


# ---------------------------------------------------------------------------
# R27.0: Paper trading (simulated fills + P/L)
# ---------------------------------------------------------------------------


@router.post("/paper/execute")
async def ui_paper_execute(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R27.0: Execute paper OPEN or CLOSE. Creates position/fill; on success writes journal entry with is_paper=true. No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    mode = (body.get("mode") or "").strip().upper()
    if mode != "PAPER":
        raise HTTPException(status_code=400, detail="mode must be PAPER")
    action = (body.get("action") or "").strip().upper()
    if action not in ("OPEN", "CLOSE"):
        raise HTTPException(status_code=400, detail="action must be OPEN or CLOSE")
    symbol = (body.get("symbol") or "").strip().upper()
    strategy = (body.get("strategy") or "SHARES").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    try:
        qty = int(body.get("qty", 0))
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive")
    ts = (body.get("ts") or "").strip() or None
    fees = 0.0
    if body.get("fees") is not None:
        try:
            fees = float(body["fees"])
        except (TypeError, ValueError):
            pass
    from app.core.paper.paper_store_r270 import paper_execute_open, paper_execute_close
    from app.core.journal.journal_store import journal_create

    try:
        if action == "OPEN":
            open_price = 0.0
            if strategy == "SHARES":
                if body.get("shares_price") is not None:
                    try:
                        open_price = float(body["shares_price"])
                    except (TypeError, ValueError):
                        pass
            else:
                if body.get("premium") is not None:
                    try:
                        open_price = float(body["premium"])
                    except (TypeError, ValueError):
                        pass
            position = paper_execute_open(
                symbol=symbol,
                strategy=strategy,
                qty=qty,
                open_price=open_price,
                open_fees=fees,
                contract_key=(body.get("contract_key") or "").strip() or None,
                expiry=(body.get("expiry") or "").strip()[:10] or None,
                strike=float(body["strike"]) if body.get("strike") is not None else None,
                right=(body.get("right") or "").strip() or None,
                ts=ts,
                notes=(body.get("notes") or "").strip()[:500] or None,
            )
            trade_date = (position.get("open_ts") or "")[:10] or (datetime.now(timezone.utc).date()).isoformat()
            tags_parts = [(body.get("tags") or "").strip()]
            sizing_hit = body.get("sizing_constraints_hit")
            if isinstance(sizing_hit, list):
                for c in sizing_hit:
                    if isinstance(c, str) and c.strip() and "FAIL" not in c and "WARN" not in c:
                        tags_parts.append("constraint:" + c.strip())
            journal_tags = ", ".join(p for p in tags_parts if p)[:500]
            journal_create(
                trade_date=trade_date,
                symbol=symbol,
                strategy=strategy,
                action="OPEN" if strategy == "SHARES" else "OPEN",
                qty=float(qty),
                price=open_price if strategy == "SHARES" else None,
                premium=open_price if strategy != "SHARES" else None,
                fees=fees,
                contract_key=position.get("contract_key"),
                expiry=position.get("expiry"),
                strike=position.get("strike"),
                right=position.get("right"),
                notes=position.get("notes"),
                tags=journal_tags or None,
                link_id=f"paper:{position.get('id')}",
                is_paper=True,
            )
            return {"status": "OK", "reason": "Paper fill recorded", "position": position}
        else:
            close_price = 0.0
            if body.get("shares_price") is not None:
                try:
                    close_price = float(body["shares_price"])
                except (TypeError, ValueError):
                    pass
            elif body.get("premium") is not None:
                try:
                    close_price = float(body["premium"])
                except (TypeError, ValueError):
                    pass
            position_id = (body.get("position_id") or "").strip() or None
            position = paper_execute_close(
                position_id=position_id,
                symbol=symbol if not position_id else None,
                strategy=strategy if not position_id else None,
                contract_key=(body.get("contract_key") or "").strip() or None,
                close_price=close_price,
                close_fees=fees,
                ts=ts,
            )
            trade_date = (position.get("close_ts") or "")[:10] or (datetime.now(timezone.utc).date()).isoformat()
            journal_create(
                trade_date=trade_date,
                symbol=symbol,
                strategy=strategy,
                action="CLOSE" if strategy == "SHARES" else "CLOSE",
                qty=float(position.get("qty", 0)),
                price=close_price if strategy == "SHARES" else None,
                premium=close_price if strategy != "SHARES" else None,
                fees=fees,
                contract_key=position.get("contract_key"),
                expiry=position.get("expiry"),
                strike=position.get("strike"),
                right=position.get("right"),
                realized_pl=position.get("realized_pl"),
                link_id=f"paper:{position.get('id')}",
                is_paper=True,
            )
            return {"status": "OK", "reason": "Paper fill recorded", "position": position}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Paper execute error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to execute paper trade")


@router.get("/paper/positions")
def ui_paper_positions(
    status: str | None = Query(None, description="OPEN or CLOSED"),
    symbol: str | None = Query(None),
    strategy: str | None = Query(None),
    include_marks: bool = Query(True, description="R27.2: Include request-time mark/unrealized for OPEN"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R27.0: List paper positions. R27.1: OPEN positions include mark_value, mark_source, mark_age_sec, quote_ts, unrealized_pl_usd. R27.2: include_marks=false for cheap call. No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    from app.core.paper.paper_store_r270 import paper_list_positions
    from app.core.paper.paper_mark_r271 import enrich_paper_positions_with_mark
    positions = paper_list_positions(status=status, symbol=symbol, strategy=strategy)
    if include_marks:
        positions = enrich_paper_positions_with_mark(positions)
    return {"positions": positions}


@router.get("/paper/positions/{position_id}")
def ui_paper_position_by_id(
    position_id: str,
    include_marks: bool = Query(True, description="R27.2: Include request-time mark for OPEN"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R27.2: Single paper position detail (enriched when OPEN and include_marks). No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    from app.core.paper.paper_store_r270 import paper_get_position
    from app.core.paper.paper_mark_r271 import enrich_paper_positions_with_mark
    pos = paper_get_position(position_id.strip())
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    if include_marks and (pos.get("status") or "").upper() == "OPEN":
        enriched = enrich_paper_positions_with_mark([pos])
        return enriched[0] if enriched else pos
    return pos


# R27.2: Dedicated close endpoint (journal action CLOSE_CSP/CLOSE_CC/SELL)
@router.post("/paper/close")
async def ui_paper_close(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R27.2: Close paper position. Body: position_id, close_price (shares) or close_premium (options), close_fees?, ts?. Journal action SELL|CLOSE_CSP|CLOSE_CC. No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    position_id = (body.get("position_id") or "").strip()
    if not position_id:
        raise HTTPException(status_code=400, detail="position_id required")
    close_price = None
    if body.get("close_price") is not None:
        try:
            close_price = float(body["close_price"])
        except (TypeError, ValueError):
            pass
    if close_price is None and body.get("close_premium") is not None:
        try:
            close_price = float(body["close_premium"])
        except (TypeError, ValueError):
            pass
    if close_price is None:
        raise HTTPException(status_code=400, detail="close_price or close_premium required")
    close_fees = 0.0
    if body.get("close_fees") is not None:
        try:
            close_fees = float(body["close_fees"])
        except (TypeError, ValueError):
            pass
    ts = (body.get("ts") or "").strip() or None
    from app.core.paper.paper_store_r270 import paper_get_position, paper_execute_close
    from app.core.journal.journal_store import journal_create
    pos_before = paper_get_position(position_id)
    if not pos_before or (pos_before.get("status") or "").upper() != "OPEN":
        raise HTTPException(status_code=404, detail="Position not found or already closed")
    strategy = (pos_before.get("strategy") or "SHARES").strip().upper()
    position = paper_execute_close(position_id=position_id, close_price=close_price, close_fees=close_fees, ts=ts)
    trade_date = (position.get("close_ts") or "")[:10] or (datetime.now(timezone.utc).date()).isoformat()
    action = "SELL" if strategy == "SHARES" else ("CLOSE_CSP" if strategy == "CSP" else "CLOSE_CC")
    existing_tags = (pos_before.get("notes") or "").strip()[:200] or ""
    tags = "paper" + (f", {existing_tags}" if existing_tags else "")
    journal_create(
        trade_date=trade_date,
        symbol=position.get("symbol", ""),
        strategy=strategy,
        action=action,
        qty=float(position.get("qty", 0)),
        price=close_price if strategy == "SHARES" else None,
        premium=close_price if strategy != "SHARES" else None,
        fees=close_fees,
        contract_key=position.get("contract_key"),
        expiry=position.get("expiry"),
        strike=position.get("strike"),
        right=position.get("right"),
        realized_pl=position.get("realized_pl"),
        link_id=f"paper:{position.get('id')}",
        is_paper=True,
        tags=tags[:500] if tags else None,
    )
    return {"status": "OK", "reason": "Paper position closed", "position": position}


@router.get("/paper/summary")
def ui_paper_summary(
    month: str = Query(..., description="YYYY-MM"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R27.0: Paper P/L summary for month. No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    month_str = (month or "").strip()[:7]
    if len(month_str) != 7 or month_str[4] != "-":
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    from app.core.paper.paper_store_r270 import paper_summary_by_month
    return paper_summary_by_month(month_str)


def _eod_summary_for_date(date_str: str) -> Dict[str, Any]:
    """Build eod-summary payload for date. No FAIL_/WARN_."""
    from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2, get_eval_snapshot
    from app.core.journal.journal_store import journal_list
    from app.api.notifications_store import get_notifications_health
    out: Dict[str, Any] = {
        "date": date_str,
        "eval_as_of": None,
        "action_needed_count": None,
        "notifications_new_count": 0,
        "journal_entries_count": 0,
    }
    try:
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        artifact = store.get_latest()
        if artifact and getattr(artifact, "metadata", None):
            out["eval_as_of"] = (artifact.metadata or {}).get("pipeline_timestamp")
        if not out["eval_as_of"]:
            snap = get_eval_snapshot()
            if isinstance(snap, dict):
                out["eval_as_of"] = snap.get("quote_as_of") or snap.get("pipeline_timestamp")
    except Exception:
        pass
    try:
        health = get_notifications_health()
        out["notifications_new_count"] = int(health.get("count_new") or 0)
    except Exception:
        pass
    try:
        entries = journal_list(from_date=date_str, to_date=date_str, limit=10000)
        out["journal_entries_count"] = len(entries)
    except Exception:
        pass
    return out


@router.get("/ops/eod-summary")
def ui_ops_eod_summary(
    date: str = Query(..., description="YYYY-MM-DD"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.4: EOD summary for date (eval as_of, counts). No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    date_str = (date or "").strip()[:10]
    if len(date_str) != 10 or date_str[4] != "-" or date_str[7] != "-":
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    return _eod_summary_for_date(date_str)


def _week_to_date_range(week_key: str) -> tuple[str, str] | None:
    """Convert YYYY-WW to (from_date, to_date) for that week (Mon-Sun)."""
    if not week_key or len(week_key) < 6:
        return None
    try:
        from datetime import datetime as _dt, timedelta
        parts = week_key.split("-")
        year = int(parts[0])
        w = int(parts[1])
        d = _dt.strptime(f"{year}-{w:02d}-1", "%G-%V-%u").date()
        end_d = d + timedelta(days=6)
        return (d.isoformat(), end_d.isoformat())
    except Exception:
        return None


@router.get("/ops/weekly-summary")
def ui_ops_weekly_summary(
    week: str = Query(..., description="YYYY-WW"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.4: Weekly summary (journal realized P/L, counts, winners/losers, guardrails). No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    week_key = (week or "").strip()
    date_range = _week_to_date_range(week_key)
    if not date_range:
        raise HTTPException(status_code=400, detail="week must be YYYY-WW")
    from_date, to_date = date_range
    from app.core.journal.journal_store import journal_list
    from app.core.portfolio.guardrails_r259 import get_guardrails_metrics_and_status
    out: Dict[str, Any] = {
        "week": week_key,
        "from_date": from_date,
        "to_date": to_date,
        "realized_pl_total": 0.0,
        "trade_count": 0,
        "winners": [],
        "losers": [],
        "guardrails": {},
    }
    try:
        entries = journal_list(from_date=from_date, to_date=to_date, limit=2000)
        out["trade_count"] = len(entries)
        realized_by_symbol: Dict[str, float] = {}
        for e in entries:
            sym = (e.get("symbol") or "").strip().upper()
            if not sym:
                continue
            pl = e.get("realized_pl")
            if pl is not None:
                try:
                    pl_f = float(pl)
                except (TypeError, ValueError):
                    continue
                out["realized_pl_total"] += pl_f
                realized_by_symbol[sym] = realized_by_symbol.get(sym, 0) + pl_f
        winners = sorted([{"symbol": s, "realized_pl": v} for s, v in realized_by_symbol.items() if v > 0], key=lambda x: -x["realized_pl"])[:10]
        losers = sorted([{"symbol": s, "realized_pl": v} for s, v in realized_by_symbol.items() if v < 0], key=lambda x: x["realized_pl"])[:10]
        out["winners"] = winners
        out["losers"] = losers
    except Exception:
        pass
    try:
        out["guardrails"] = get_guardrails_metrics_and_status()
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# R25.5: Journal + Monthly Reports (SQLite-backed; no FAIL/WARN in responses)
# ---------------------------------------------------------------------------


@router.get("/journal")
def ui_journal_list(
    from_date: str | None = Query(None, description="YYYY-MM-DD"),
    to_date: str | None = Query(None, description="YYYY-MM-DD"),
    symbol: str | None = Query(None),
    strategy: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_paper: bool = Query(True, description="R27.0: Include paper trades"),
    paper_only: bool = Query(False, description="R27.2: Only paper entries"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.5: List journal entries (ordered by created_ts desc). R27.0: include_paper. R27.2: paper_only. R27.4: link_target (request-time)."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.journal.journal_store import journal_list
        from app.core.journal.journal_links_r274 import parse_link_id
        entries = journal_list(from_date=from_date, to_date=to_date, symbol=symbol, strategy=strategy, limit=limit, offset=offset, include_paper=include_paper, paper_only=paper_only)
        for e in entries:
            e["link_target"] = parse_link_id(e.get("link_id"))
        return {"entries": entries}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Journal list error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to load journal entries")


@router.post("/journal")
async def ui_journal_create(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.5: Create journal entry. Body: trade_date, symbol, strategy, action, qty, price|premium, fees?, contract_key?, notes?, tags?, link_id?."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    trade_date = (body.get("trade_date") or "").strip()[:10]
    symbol = (body.get("symbol") or "").strip().upper()
    strategy = (body.get("strategy") or "SHARES").strip().upper()
    action = (body.get("action") or "").strip().upper()
    if not trade_date or not symbol or not action:
        raise HTTPException(status_code=400, detail="trade_date, symbol, and action required")
    try:
        qty = float(body.get("qty", 0))
    except (TypeError, ValueError):
        qty = 0.0
    price = body.get("price")
    premium = body.get("premium")
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None
    if premium is not None:
        try:
            premium = float(premium)
        except (TypeError, ValueError):
            premium = None
    fees = body.get("fees")
    if fees is not None:
        try:
            fees = float(fees)
        except (TypeError, ValueError):
            fees = None
    strike_val = None
    if body.get("strike") is not None:
        try:
            strike_val = float(body["strike"])
        except (TypeError, ValueError):
            pass
    realized_val = None
    if body.get("realized_pl") is not None:
        try:
            realized_val = float(body["realized_pl"])
        except (TypeError, ValueError):
            pass
    try:
        from app.core.journal.journal_store import journal_create
        entry = journal_create(
            trade_date=trade_date,
            symbol=symbol,
            strategy=strategy,
            action=action,
            qty=qty,
            price=price,
            premium=premium,
            fees=fees,
            contract_key=(body.get("contract_key") or "").strip() or None,
            expiry=(body.get("expiry") or "").strip()[:10] or None,
            strike=strike_val,
            right=(body.get("right") or "").strip() or None,
            notes=(body.get("notes") or "").strip()[:2000] or None,
            tags=(body.get("tags") or "").strip()[:500] or None,
            realized_pl=realized_val,
            link_id=(body.get("link_id") or "").strip() or None,
        )
        return {"entry": entry}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Journal create error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to create entry")


# R27.3: Record options close/roll in Journal only (no execution)
@router.post("/journal/record-close")
async def ui_journal_record_close(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R27.3: Record CLOSE_CSP/CLOSE_CC/ROLL in Journal. Body: symbol, strategy (CSP|CC), action (CLOSE_CSP|CLOSE_CC|ROLL), qty, premium, contract_key?, expiry?, strike?, right?, fees?, notes?, trade_date?. No execution. No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(body, dict):
        body = {}
    symbol = (body.get("symbol") or "").strip().upper()
    strategy = (body.get("strategy") or "CSP").strip().upper()
    if strategy not in ("CSP", "CC"):
        raise HTTPException(status_code=400, detail="strategy must be CSP or CC")
    action = (body.get("action") or "CLOSE_CSP").strip().upper()
    if action not in ("CLOSE_CSP", "CLOSE_CC", "ROLL"):
        raise HTTPException(status_code=400, detail="action must be CLOSE_CSP, CLOSE_CC, or ROLL")
    try:
        qty = float(body.get("qty", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="qty required and must be a number")
    premium = None
    if body.get("premium") is not None:
        try:
            premium = float(body["premium"])
        except (TypeError, ValueError):
            pass
    fees = None
    if body.get("fees") is not None:
        try:
            fees = float(body["fees"])
        except (TypeError, ValueError):
            pass
    trade_date = (body.get("trade_date") or "").strip()[:10] or (datetime.now(timezone.utc).date()).isoformat()
    contract_key = (body.get("contract_key") or "").strip() or None
    expiry = (body.get("expiry") or "").strip()[:10] or None
    strike = None
    if body.get("strike") is not None:
        try:
            strike = float(body["strike"])
        except (TypeError, ValueError):
            pass
    right = (body.get("right") or "").strip() or None
    notes = (body.get("notes") or "").strip()[:2000] or None
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    try:
        from app.core.journal.journal_store import journal_create
        entry = journal_create(
            trade_date=trade_date,
            symbol=symbol,
            strategy=strategy,
            action=action,
            qty=qty,
            price=None,
            premium=premium,
            fees=fees,
            contract_key=contract_key,
            expiry=expiry,
            strike=strike,
            right=right,
            realized_pl=None,
            link_id=None,
            is_paper=False,
            notes=notes,
        )
        return {"status": "OK", "entry": entry}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Journal record-close error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to create entry")


@router.patch("/journal/{entry_id}")
async def ui_journal_update(
    entry_id: str,
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.5: Update journal entry (notes, tags, fees, trade_date, qty, price, premium)."""
    _require_ui_key(x_ui_key)
    if not entry_id or not entry_id.strip():
        raise HTTPException(status_code=400, detail="entry_id required")
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    def _opt_float(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    try:
        from app.core.journal.journal_store import journal_update
        updated = journal_update(
            entry_id.strip(),
            notes=body.get("notes"),
            tags=body.get("tags"),
            fees=_opt_float(body.get("fees")),
            trade_date=(body.get("trade_date") or "").strip()[:10] or None,
            qty=_opt_float(body.get("qty")),
            price=_opt_float(body.get("price")),
            premium=_opt_float(body.get("premium")),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Entry not found")
        return {"entry": updated}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Journal update error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to update entry")


@router.post("/journal/export")
def ui_journal_export(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
):
    """R25.5: Export journal as CSV."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.journal.journal_store import journal_export_csv
        csv_str = journal_export_csv(from_date=from_date.strip()[:10], to_date=to_date.strip()[:10])
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(csv_str, media_type="text/csv")
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Journal export error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to export")


@router.get("/reports/monthly")
def ui_reports_monthly(
    month: str = Query(..., description="YYYY-MM"),
    include_paper: bool = Query(False, description="R27.0: Include paper trades in aggregate"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R25.5: Monthly report aggregate. R27.0: include_paper. R27.1: response includes included_paper and mode (LIVE_ONLY|PAPER_ONLY|MIXED). Safe response only."""
    _require_ui_key(x_ui_key)
    month = (month or "").strip()[:7]
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    try:
        from app.core.journal.journal_store import journal_monthly_aggregate, journal_monthly_paper_live_counts
        data = journal_monthly_aggregate(month, include_paper=include_paper)
        data["included_paper"] = include_paper
        if not include_paper:
            data["mode"] = "LIVE_ONLY"
        else:
            live_count, paper_count = journal_monthly_paper_live_counts(month)
            if live_count and paper_count:
                data["mode"] = "MIXED"
            elif paper_count:
                data["mode"] = "PAPER_ONLY"
            else:
                data["mode"] = "LIVE_ONLY"
            # R27.2: Split totals when include_paper enabled
            data["live_totals"] = journal_monthly_aggregate(month, include_paper=False)
            data["paper_totals"] = journal_monthly_aggregate(month, include_paper=True, paper_only=True)
        return data
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Monthly report error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to load report")


# R26.5: Monthly close pack (data/reports/<month>/; state + files + download)
def _monthly_close_allowlist() -> frozenset:
    from app.core.ops.monthly_close_store_r265 import ALLOWED_FILES
    return ALLOWED_FILES


@router.post("/reports/monthly/close")
def ui_reports_monthly_close(
    month: str = Query(..., description="YYYY-MM"),
    include_paper: bool = Query(False, description="R27.1: Generate paper pack (data/reports/<month>/paper/)"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.5: Generate monthly close pack. R27.1: include_paper=false -> live/ subdir, true -> paper/ subdir."""
    _require_ui_key(x_ui_key)
    month = (month or "").strip()[:7]
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    try:
        from app.core.ops.monthly_close_store_r265 import generate_monthly_close_pack
        result = generate_monthly_close_pack(month, include_paper=include_paper)
        return {"status": "OK", "month": result["month"], "pack": result.get("pack", "live"), "generated_ts": result["generated_ts"], "paths": result["paths"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Monthly close pack error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to generate close pack")


@router.get("/reports/monthly/close/files")
def ui_reports_monthly_close_files(
    month: str = Query(..., description="YYYY-MM"),
    pack: str = Query("live", description="R27.1: live or paper"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R26.5: List available close pack files and sizes for month. R27.1: pack=live|paper for subdir."""
    _require_ui_key(x_ui_key)
    month = (month or "").strip()[:7]
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    pack = (pack or "live").strip().lower()
    if pack not in ("live", "paper"):
        pack = "live"
    try:
        from app.core.ops.monthly_close_store_r265 import _reports_base_path, ALLOWED_FILES, monthly_close_get
        base = _reports_base_path()
        month_dir = base / month / pack
        files: List[Dict[str, Any]] = []
        if month_dir.exists():
            for name in sorted(ALLOWED_FILES):
                p = month_dir / name
                if p.is_file():
                    files.append({"name": name, "size": p.stat().st_size})
        state = monthly_close_get(month, pack=pack)
        out: Dict[str, Any] = {"month": month, "pack": pack, "files": files}
        if state:
            out["generated_ts"] = state.get("generated_ts")
            out["paths"] = state.get("paths_json") or []
        return out
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Monthly close files error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to list files")


@router.get("/reports/monthly/close/download")
def ui_reports_monthly_close_download(
    month: str = Query(..., description="YYYY-MM"),
    file: str = Query(..., description="File name (allowlist)"),
    pack: str = Query("live", description="R27.1: live or paper"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
):
    """R26.5: Stream close pack file; file validated against allowlist. R27.1: pack=live|paper for subdir; no path traversal."""
    _require_ui_key(x_ui_key)
    month = (month or "").strip()[:7]
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    pack = (pack or "live").strip().lower()
    if pack not in ("live", "paper"):
        pack = "live"
    allowlist = _monthly_close_allowlist()
    file_name = (file or "").strip()
    if file_name not in allowlist:
        raise HTTPException(status_code=400, detail="Invalid file name")
    try:
        from app.core.ops.monthly_close_store_r265 import _reports_base_path
        from fastapi.responses import FileResponse
        base = _reports_base_path()
        path = (base / month / pack / file_name).resolve()
        expected_dir = (base / month / pack).resolve()
        if not path.is_file() or path.parent != expected_dir or path.name != file_name:
            raise HTTPException(status_code=404, detail="File not found")
        media = "application/json" if file_name.endswith(".json") else "text/csv" if file_name.endswith(".csv") else "text/plain"
        return FileResponse(path, media_type=media, filename=file_name)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Monthly close download error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to download")


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


# ---------------------------------------------------------------------------
# Phase 21.1: Account summary, balances, holdings (manual entry, SQLite)
# ---------------------------------------------------------------------------


@router.get("/account/summary")
def ui_account_summary(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Get account summary: balances, holdings count, timestamps (default account from SQLite)."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.holdings_db import get_account_summary
        return get_account_summary()
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error getting account summary: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account/holdings")
def ui_account_holdings(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """List holdings for default account (symbol, shares, avg_cost, updated_at)."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.holdings_db import list_holdings
        return {"holdings": list_holdings()}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error listing holdings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/account/holdings")
async def ui_account_holdings_upsert(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Add or update a holding. Body: symbol (required), shares (required), avg_cost (optional)."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.holdings_db import upsert_holding
        body = await request.json()
        symbol = (body.get("symbol") or "").strip()
        shares = body.get("shares")
        avg_cost = body.get("avg_cost")
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        if shares is None:
            raise HTTPException(status_code=400, detail="shares is required")
        try:
            shares = int(shares)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="shares must be an integer")
        holding = upsert_holding(symbol=symbol, shares=shares, avg_cost=avg_cost)
        return {"holding": holding}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error upserting holding: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/account/holdings/{symbol}")
def ui_account_holdings_delete(
    symbol: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Remove holding for symbol."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.holdings_db import delete_holding
        deleted = delete_holding(symbol)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Holding for {symbol} not found")
        return {"deleted": True, "symbol": symbol.strip().upper()}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error deleting holding: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/account/balances")
async def ui_account_balances_set(
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Set cash and buying_power for default account (manual). Body: cash, buying_power."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.holdings_db import set_balances
        body = await request.json()
        cash = body.get("cash")
        buying_power = body.get("buying_power")
        if cash is None and buying_power is None:
            raise HTTPException(status_code=400, detail="At least one of cash or buying_power is required")
        cash = float(cash) if cash is not None else 0.0
        buying_power = float(buying_power) if buying_power is not None else 0.0
        summary = set_balances(cash=cash, buying_power=buying_power)
        return {"summary": summary}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error setting balances: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
        # R23.0: Include share positions (qty, avg_cost, last_price when available from artifact). R27.4: mark/unrealized.
        shares_positions_out: List[Dict[str, Any]] = []
        try:
            from app.core.accounts.holdings_db import list_share_positions
            from app.core.accounts.holdings_db import _DEFAULT_ACCOUNT_ID
            from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
            from app.core.portfolio.live_shares_mark_r274 import enrich_live_shares_positions_with_mark
            store = get_evaluation_store_v2()
            store.reload_from_disk()
            artifact = store.get_latest()
            price_by_symbol: Dict[str, float] = {}
            quote_ts_iso: Optional[str] = None
            if artifact:
                meta = getattr(artifact, "metadata", None) or {}
                quote_ts_iso = meta.get("pipeline_timestamp")
                if getattr(artifact, "symbols", None):
                    for s in artifact.symbols:
                        sym = (getattr(s, "symbol", "") or "").strip().upper()
                        if not sym:
                            continue
                        p = getattr(s, "price", None) or getattr(s, "underlying_price", None)
                        if p is not None:
                            try:
                                price_by_symbol[sym] = float(p)
                            except (TypeError, ValueError):
                                pass
            raw_shares: List[Dict[str, Any]] = []
            for pos in list_share_positions(_DEFAULT_ACCOUNT_ID):
                last_price = price_by_symbol.get(pos["symbol"])
                qty = pos.get("quantity") or 0
                avg_cost = pos.get("avg_cost")
                market_value = (last_price * qty) if last_price is not None and qty else None
                unrealized_pnl = (last_price - avg_cost) * qty if (last_price is not None and avg_cost is not None and qty) else None
                raw_shares.append({
                    "symbol": pos["symbol"],
                    "quantity": qty,
                    "avg_cost": pos.get("avg_cost"),
                    "last_price": last_price,
                    "market_value": round(market_value, 2) if market_value is not None else None,
                    "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
                    "updated_at": pos.get("updated_at"),
                })
            shares_positions_out = enrich_live_shares_positions_with_mark(raw_shares, price_by_symbol, quote_ts_iso)
        except Exception:
            pass
        return {
            "positions": out,
            "capital_deployed": round(capital_deployed, 2),
            "open_positions_count": open_count,
            "shares_positions": shares_positions_out,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading portfolio: %s", e)
        return {"positions": [], "capital_deployed": 0, "open_positions_count": 0, "shares_positions": []}


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


@router.get("/wheel/overview")
def ui_wheel_overview(
    account_id: str | None = Query(default=None, description="Account ID; omit for default"),
    exclude_test: bool = Query(default=True),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 18.0: Wheel lifecycle overview.
    Returns per-symbol: wheel_state, next_action, risk_status, last_decision_score, links (run_id), open_position.
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.store import get_account, get_default_account
        from app.core.positions.service import list_positions
        from app.core.portfolio.risk import evaluate_portfolio_risk
        from app.core.wheel.state_store import load_state
        from app.core.wheel.next_action import compute_next_action

        account = get_account(account_id.strip()) if account_id else None
        if account is None:
            account = get_default_account()
        if account is None:
            return {"symbols": {}, "risk_status": "FAIL", "error": "No account found"}

        positions = list_positions(status=None, symbol=None, exclude_test=exclude_test)
        if account_id:
            positions = [p for p in positions if (p.account_id or "").strip() == account_id.strip()]
        open_pos = [p for p in positions if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT")]
        portfolio_risk = evaluate_portfolio_risk(account, open_pos)
        risk_status = (portfolio_risk.get("status") or "PASS").upper()

        wheel_state_data = load_state()
        symbols_map = wheel_state_data.get("symbols") or {}
        last_wheel_actions: Dict[str, Dict[str, Any]] = {}
        try:
            from app.core.wheel.actions_store import get_last_wheel_action_per_symbol
            last_wheel_actions = get_last_wheel_action_per_symbol()
        except Exception:
            pass

        artifact = None
        run_id = None
        try:
            from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
            store = get_evaluation_store_v2()
            store.reload_from_disk()
            artifact = store.get_latest()
            if artifact and artifact.metadata:
                run_id = artifact.metadata.get("run_id")
        except Exception:
            pass

        open_by_symbol: Dict[str, Any] = {}
        for p in open_pos:
            sym = (getattr(p, "symbol", "") or "").strip().upper()
            if sym:
                open_by_symbol.setdefault(sym, []).append(p)

        symbol_scores: Dict[str, Any] = {}
        if artifact and artifact.symbols:
            for s in artifact.symbols:
                sym = (getattr(s, "symbol", "") or "").strip().upper()
                if sym:
                    symbol_scores[sym] = {
                        "score": getattr(s, "score", None) or getattr(s, "final_score", None),
                        "band": getattr(s, "band", None),
                        "verdict": getattr(s, "verdict", None),
                    }

        def _candidate_to_dict(c: Any) -> Dict[str, Any]:
            if c is None:
                return {}
            if isinstance(c, dict):
                return {k: c.get(k) for k in ("strategy", "expiry", "strike", "delta", "credit_estimate", "max_loss", "contract_key", "option_symbol", "why_this_trade") if c.get(k) is not None}
            return {
                "strategy": getattr(c, "strategy", None),
                "expiry": getattr(c, "expiry", None) or getattr(c, "expiration", None),
                "strike": getattr(c, "strike", None),
                "delta": getattr(c, "delta", None),
                "credit_estimate": getattr(c, "credit_estimate", None),
                "max_loss": getattr(c, "max_loss", None),
                "contract_key": getattr(c, "contract_key", None),
                "option_symbol": getattr(c, "option_symbol", None),
                "why_this_trade": getattr(c, "why_this_trade", None),
            }

        all_symbols = set(symbols_map.keys()) | set(open_by_symbol.keys()) | set(symbol_scores.keys())
        rows: Dict[str, Dict[str, Any]] = {}
        for sym in sorted(all_symbols):
            ws = symbols_map.get(sym) or {"state": "EMPTY", "last_updated_utc": None, "linked_position_ids": []}
            next_action = compute_next_action(
                sym, ws, artifact, portfolio_risk,
                account=account, open_positions=open_pos,
            )
            suggested_candidate = None
            ck = next_action.get("suggested_contract_key")
            if ck and artifact and hasattr(artifact, "candidates_by_symbol"):
                cands = artifact.candidates_by_symbol.get(sym) or []
                for c in cands:
                    if (getattr(c, "contract_key", None) or (c.get("contract_key") if isinstance(c, dict) else None)) == ck:
                        suggested_candidate = _candidate_to_dict(c)
                        break
                if not suggested_candidate and cands:
                    suggested_candidate = _candidate_to_dict(cands[0])
            open_plist = open_by_symbol.get(sym) or []
            pos_info = None
            if open_plist:
                p0 = open_plist[0]
                pos_info = {
                    "position_id": getattr(p0, "position_id", None),
                    "contract_key": getattr(p0, "contract_key", None),
                    "strategy": getattr(p0, "strategy", None),
                    "contracts": getattr(p0, "contracts", None),
                }
            score_info = symbol_scores.get(sym) or {}
            last_action = last_wheel_actions.get(sym)
            manual_override = bool(last_action and last_action.get("action") in ("ASSIGNED", "UNASSIGNED", "RESET"))
            rows[sym] = {
                "symbol": sym,
                "wheel_state": ws.get("state", "EMPTY"),
                "last_updated_utc": ws.get("last_updated_utc"),
                "manual_override": manual_override,
                "last_wheel_action": last_action,
                "linked_position_ids": ws.get("linked_position_ids") or [],
                "next_action": next_action,
                "suggested_candidate": suggested_candidate,
                "risk_status": risk_status,
                "last_decision_score": score_info.get("score"),
                "last_decision_band": score_info.get("band"),
                "last_decision_verdict": score_info.get("verdict"),
                "links": {"run_id": run_id},
                "open_position": pos_info,
            }
        wheel_integrity: Optional[Dict[str, Any]] = None
        try:
            from app.api.diagnostics import _run_wheel_state_integrity_check
            wheel_integrity = _run_wheel_state_integrity_check()
        except Exception:
            pass
        payload: Dict[str, Any] = {
            "symbols": rows,
            "risk_status": risk_status,
            "run_id": run_id,
        }
        if wheel_integrity is not None:
            payload["wheel_integrity"] = {
                "status": wheel_integrity.get("status"),
                "recommended_action": wheel_integrity.get("recommended_action"),
                "details": wheel_integrity.get("details"),
            }
        return payload
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading wheel overview: %s", e)
        return {"symbols": {}, "risk_status": "FAIL", "error": str(e)}


def _wheel_notify(symbol: str, subtype: str, message: str) -> None:
    """Phase 20.0: Append WHEEL_STATE notification."""
    try:
        from app.api.notifications_store import append_notification
        append_notification("INFO", "WHEEL_STATE", message, symbol=symbol, subtype=subtype)
    except Exception:
        pass


@router.post("/wheel/{symbol}/assign")
def ui_wheel_assign(
    symbol: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 20.0: Manual assign — set wheel state to ASSIGNED for symbol."""
    _require_ui_key(x_ui_key)
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    try:
        from app.core.wheel.actions_store import append_wheel_action
        from app.core.wheel.state_machine import update_state_from_position_event
        append_wheel_action(symbol, "ASSIGNED")
        new_state = update_state_from_position_event(symbol, "ASSIGNED", "")
        _wheel_notify(symbol, "ASSIGNED", f"Wheel state set to ASSIGNED for {symbol}")
        return {"symbol": symbol, "state": new_state}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Wheel assign failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wheel/{symbol}/unassign")
def ui_wheel_unassign(
    symbol: str,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 20.0: Manual unassign — set wheel state to EMPTY for symbol."""
    _require_ui_key(x_ui_key)
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    try:
        from app.core.wheel.actions_store import append_wheel_action
        from app.core.wheel.state_machine import update_state_from_position_event
        append_wheel_action(symbol, "UNASSIGNED")
        new_state = update_state_from_position_event(symbol, "UNASSIGNED", "")
        _wheel_notify(symbol, "UNASSIGNED", f"Wheel state set to EMPTY for {symbol}")
        return {"symbol": symbol, "state": new_state}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Wheel unassign failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wheel/{symbol}/reset")
async def ui_wheel_reset(
    symbol: str,
    request: Request,
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """Phase 20.0: Reset — clear wheel state entry for symbol (positions unchanged). Requires body {confirm: true}."""
    _require_ui_key(x_ui_key)
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol required")
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        body = {}
    if body.get("confirm") is not True:
        raise HTTPException(status_code=400, detail="Body must include { \"confirm\": true }")
    try:
        from app.core.wheel.actions_store import append_wheel_action
        from app.core.wheel.state_store import clear_symbol_from_state
        append_wheel_action(symbol, "RESET")
        clear_symbol_from_state(symbol)
        _wheel_notify(symbol, "RESET", f"Wheel state cleared for {symbol}")
        return {"symbol": symbol, "state": "cleared"}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Wheel reset failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wheel/repair")
def ui_wheel_repair(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
    exclude_test: bool = Query(default=True),
) -> Dict[str, Any]:
    """Phase 20.0: Rebuild wheel_state from open positions and wheel actions. Returns repaired_symbols, removed_symbols, status."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        from app.core.wheel.repair import repair_wheel_state
        from app.api.notifications_store import append_notification
        positions = list_positions(status=None, symbol=None, exclude_test=exclude_test)
        open_pos = [p for p in positions if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT")]
        result = repair_wheel_state(open_pos)
        append_notification(
            "INFO", "WHEEL_STATE", "Wheel state repaired from open positions.",
            subtype="REPAIRED", details=result,
        )
        return result
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Wheel repair failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/marks/refresh")
def ui_positions_marks_refresh(
    account_id: str | None = Query(default=None, description="Account ID; omit for all"),
    exclude_test: bool = Query(default=True),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Phase 15.0: Refresh marks for OPEN positions from provider. Returns {updated_count, skipped_count, errors}.
    Phase 16.0: Writes out/mark_refresh_state.json; on FAIL appends MARK_REFRESH_FAILED notification (1/hr).
    """
    _require_ui_key(x_ui_key)
    try:
        from app.core.positions.service import list_positions
        from app.core.portfolio.marking import refresh_marks
        from app.core.portfolio.mark_refresh_state import write_mark_refresh_state, maybe_append_mark_refresh_failed_notification
        positions = list_positions(status=None, symbol=None, exclude_test=exclude_test)
        if account_id:
            positions = [p for p in positions if (p.account_id or "").strip() == account_id.strip()]
        open_pos = [p for p in positions if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT")]
        updated, skipped, errors = refresh_marks(open_pos, account_id=account_id)
        write_mark_refresh_state(updated, skipped, errors)
        maybe_append_mark_refresh_failed_notification(updated, errors)
        return {"updated_count": updated, "skipped_count": skipped, "errors": errors}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error refreshing marks: %s", e)
        write_mark_refresh_state(0, 0, [str(e)])
        maybe_append_mark_refresh_failed_notification(0, [str(e)])
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
        # R23.0: Include share positions with optional last_price from artifact
        shares_out: List[Dict[str, Any]] = []
        try:
            from app.core.accounts.holdings_db import list_share_positions, _DEFAULT_ACCOUNT_ID
            from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
            store = get_evaluation_store_v2()
            store.reload_from_disk()
            art = store.get_latest()
            price_by_sym: Dict[str, float] = {}
            if art and getattr(art, "symbols", None):
                for s in art.symbols:
                    sym = (getattr(s, "symbol", "") or "").strip().upper()
                    if sym:
                        p = getattr(s, "price", None) or getattr(s, "underlying_price", None)
                        if p is not None:
                            try:
                                price_by_sym[sym] = float(p)
                            except (TypeError, ValueError):
                                pass
            for pos in list_share_positions(account_id or _DEFAULT_ACCOUNT_ID):
                last_price = price_by_sym.get(pos["symbol"])
                qty = pos.get("quantity") or 0
                avg = pos.get("avg_cost")
                mv = (last_price * qty) if last_price is not None and qty else None
                unpnl = (last_price - avg) * qty if (last_price is not None and avg is not None and qty) else None
                shares_out.append({
                    "symbol": pos["symbol"],
                    "quantity": qty,
                    "avg_cost": avg,
                    "last_price": last_price,
                    "market_value": round(mv, 2) if mv is not None else None,
                    "unrealized_pnl": round(unpnl, 2) if unpnl is not None else None,
                })
        except Exception:
            pass
        return {
            "realized_total": round(realized_total, 2),
            "unrealized_total": round(unrealized_total, 2),
            "positions": per_position,
            "shares_positions": shares_out,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error loading portfolio MTM: %s", e)
        return {"realized_total": 0, "unrealized_total": 0, "positions": [], "shares_positions": []}


# ---------------------------------------------------------------------------
# R23.0: Share positions (shares holdings per symbol; used for CC eligibility + Portfolio)
# ---------------------------------------------------------------------------


@router.get("/shares/positions")
def ui_shares_positions_list(
    account_id: str = Query(..., description="Account ID"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R23.0: List share positions for account."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.holdings_db import list_share_positions
        positions = list_share_positions(account_id)
        return {"account_id": account_id, "positions": positions}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error listing share positions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shares/positions/closed")
def ui_shares_positions_closed_list(
    account_id: str = Query(..., description="Account ID"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R23.5.0: List closed share positions for account. Must be before /{symbol} route."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.holdings_db import list_closed_share_positions
        positions = list_closed_share_positions(account_id)
        return {"account_id": account_id, "positions": positions}
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error listing closed share positions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shares/positions/{symbol}")
def ui_shares_position_get(
    symbol: str = Path(..., min_length=1, max_length=12),
    account_id: str = Query(..., description="Account ID"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R23.0: Get single share position for account+symbol. 404 if none."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.holdings_db import get_share_position
        pos = get_share_position(account_id, symbol)
        if pos is None:
            raise HTTPException(status_code=404, detail=f"No share position for {symbol}")
        return pos
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error getting share position: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shares/positions/{symbol}")
async def ui_shares_position_upsert(
    symbol: str = Path(..., min_length=1, max_length=12),
    account_id: str | None = Query(default=None),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
    request: Request = None,
) -> Dict[str, Any]:
    """R23.0: Upsert share position. Body: { account_id, quantity, avg_cost?, opened_at? }."""
    _require_ui_key(x_ui_key)
    try:
        body: Dict[str, Any] = {}
        if request and request.headers.get("content-type", "").strip().lower().startswith("application/json"):
            body = await request.json() or {}
        if not isinstance(body, dict):
            body = {}
        aid = (body.get("account_id") or account_id or "").strip()
        if not aid:
            raise HTTPException(status_code=400, detail="account_id is required")
        qty = body.get("quantity")
        if qty is None:
            raise HTTPException(status_code=400, detail="quantity is required")
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="quantity must be an integer")
        if qty < 0:
            raise HTTPException(status_code=400, detail="quantity must be non-negative")
        avg_cost = body.get("avg_cost")
        if avg_cost is not None:
            try:
                avg_cost = float(avg_cost)
            except (TypeError, ValueError):
                avg_cost = None
        opened_at = body.get("opened_at")
        if opened_at is not None and not isinstance(opened_at, str):
            opened_at = None
        target_price = body.get("target_price")
        if target_price is not None:
            try:
                target_price = float(target_price)
            except (TypeError, ValueError):
                target_price = None
        stop_price = body.get("stop_price")
        if stop_price is not None:
            try:
                stop_price = float(stop_price)
            except (TypeError, ValueError):
                stop_price = None
        from app.core.accounts.holdings_db import upsert_share_position
        pos = upsert_share_position(aid, symbol, qty, avg_cost=avg_cost, opened_at=opened_at, target_price=target_price, stop_price=stop_price)
        return pos
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error upserting share position: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/shares/positions/{symbol}")
def ui_shares_position_delete(
    symbol: str = Path(..., min_length=1, max_length=12),
    account_id: str = Query(..., description="Account ID"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R23.0: Delete share position for account+symbol."""
    _require_ui_key(x_ui_key)
    try:
        from app.core.accounts.holdings_db import delete_share_position
        deleted = delete_share_position(account_id, symbol)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"No share position for {symbol}")
        return {"deleted": True, "symbol": symbol.strip().upper()}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error deleting share position: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shares/positions/{symbol}/close")
async def ui_shares_position_close(
    symbol: str = Path(..., min_length=1, max_length=12),
    account_id: str | None = Query(default=None),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
    request: Request = None,
) -> Dict[str, Any]:
    """R23.5.0: Close share position. R27.3: Body exit_price, exit_date? (ts), fees?, notes?; auto-create journal entry is_paper=false, SELL, link_id=shares:{symbol}:{id}. No FAIL_/WARN_."""
    _require_ui_key(x_ui_key)
    try:
        body: Dict[str, Any] = {}
        if request and request.headers.get("content-type", "").strip().lower().startswith("application/json"):
            body = await request.json() or {}
        if not isinstance(body, dict):
            body = {}
        aid = (body.get("account_id") or account_id or "").strip() or "default"
        exit_price = body.get("exit_price")
        if exit_price is None:
            raise HTTPException(status_code=400, detail="exit_price is required")
        try:
            exit_price_f = float(exit_price)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="exit_price must be a number")
        exit_date = body.get("exit_date") or body.get("ts")
        if exit_date is not None and not isinstance(exit_date, str):
            exit_date = None
        notes = body.get("notes")
        if notes is not None and not isinstance(notes, str):
            notes = None
        fees_val = 0.0
        if body.get("fees") is not None:
            try:
                fees_val = float(body["fees"])
            except (TypeError, ValueError):
                pass
        from app.core.accounts.holdings_db import close_share_position
        from app.core.journal.journal_store import journal_create
        closed = close_share_position(aid, symbol.strip().upper(), exit_price_f, exit_date=exit_date, notes=notes)
        trade_date = (closed.get("closed_at") or "")[:10] or (datetime.now(timezone.utc).date()).isoformat()
        realized_for_journal = (closed.get("realized_pnl") or 0) - fees_val
        journal_create(
            trade_date=trade_date,
            symbol=closed.get("symbol", symbol.strip().upper()),
            strategy="SHARES",
            action="SELL",
            qty=float(closed.get("quantity", 0)),
            price=exit_price_f,
            fees=fees_val,
            realized_pl=round(realized_for_journal, 2),
            link_id=f"shares:{closed.get('symbol', symbol)}:{closed.get('id')}",
            is_paper=False,
            notes=(notes or "").strip()[:2000] or None,
        )
        return closed
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error closing share position: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
            status = 409 if any("Wheel policy" in (e or "") for e in errors) else 400
            raise HTTPException(status_code=status, detail={"errors": errors})
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


def _reason_code_to_label(code: str) -> str:
    """R22.7: Map machine code to safe display label (no FAIL_/WARN_ in output)."""
    c = (code or "").strip().upper()
    if not c:
        return ""
    labels = {
        "REGIME_CONFLICT": "Regime conflict",
        "NOT_NEAR_SUPPORT": "Not near support",
        "NOT_NEAR_RESISTANCE": "Not near resistance",
        "NO_SUPPORT": "No support level",
        "NO_RESISTANCE": "No resistance level",
        "RSI_RANGE": "RSI out of range",
        "RSI_CSP": "RSI (CSP) out of range",
        "RSI_CC": "RSI (CC) out of range",
        "ATR": "ATR check",
        "ATR_TOO_HIGH": "ATR too high",
        "NO_HOLDINGS": "No holdings",
        "NOT_HELD_FOR_CC": "Not held for CC",
        "REGIME_CSP": "Regime (CSP)",
        "REGIME_CC": "Regime (CC)",
        "NO_CANDLES": "No candles",
    }
    return labels.get(c, code.replace("_", " ").title())


def _primary_reason_display(summary: Any) -> str:
    """R22.7: Request-time display string from primary_reason_codes or primary_reason (no raw FAIL_* in output)."""
    codes = getattr(summary, "primary_reason_codes", None) or []
    if not codes and getattr(summary, "primary_reason", None):
        from app.core.eval.decision_artifact_v2 import _reason_string_to_codes
        codes = _reason_string_to_codes(getattr(summary, "primary_reason", None))
    if codes:
        return "; ".join(_reason_code_to_label(c) for c in codes)
    return getattr(summary, "primary_reason", None) or ""


def _compute_reasons_explained(
    primary_reason: Optional[str],
    symbol_eligibility: Dict[str, Any],
    sample_rejected_due_to_delta: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compute reasons_explained on-demand for API (not persisted). Uses code + sample only."""
    try:
        from app.core.eval.reason_codes import explain_reasons
        top_rej = {"sample_rejected_due_to_delta": sample_rejected_due_to_delta} if sample_rejected_due_to_delta else None
        return explain_reasons(primary_reason or "", symbol_eligibility, {}, top_rej)
    except Exception:
        return []


def _build_mtf_levels_at_request_time(
    symbol: str,
    technicals: Dict[str, Any],
    exit_plan: Dict[str, Any],
    as_of_iso: Optional[str],
) -> Dict[str, Any]:
    """R22.7: Multi-timeframe S/R from resampled OHLC. Daily from technicals or recomputed; weekly/monthly from resampled bars."""
    support = technicals.get("support_level")
    resistance = technicals.get("resistance_level")
    as_of = as_of_iso or ""
    method = "swing_cluster"
    daily_block: Optional[Dict[str, Any]] = (
        {"support": support, "resistance": resistance, "as_of": as_of, "method": method, "bar_count": None}
        if (support is not None or resistance is not None) else None
    )
    weekly_block: Optional[Dict[str, Any]] = None
    monthly_block: Optional[Dict[str, Any]] = None
    min_bars = 7  # 2*k+1 with k=3
    try:
        from app.core.eligibility.candles import get_candles
        from app.core.eligibility.multiframe import _resample_daily_to_weekly, _resample_daily_to_monthly
        from app.core.eligibility.swing_cluster import compute_support_resistance
        from app.core.eligibility.config import (
            SWING_CLUSTER_WINDOW,
            SWING_FRACTAL_K,
            S_R_ATR_MULT,
            S_R_PCT_TOL,
        )
        daily_candles = get_candles((symbol or "").strip().upper(), "daily", 400)
        spot = technicals.get("spot")
        if spot is None and daily_candles:
            last = daily_candles[-1]
            try:
                spot = float(last.get("close") or last.get("open") or 0)
            except (TypeError, ValueError):
                spot = 0.0
        atr14 = technicals.get("atr")
        if not daily_candles or spot <= 0:
            return {"monthly": monthly_block or _insufficient("monthly"), "weekly": weekly_block or _insufficient("weekly"), "daily": daily_block, "4h": None}

        # Daily S/R from artifact technicals (already computed at eval) or from candles
        if daily_block is None and len(daily_candles) >= min_bars:
            sr_d = compute_support_resistance(
                daily_candles, float(spot), atr14, SWING_CLUSTER_WINDOW, SWING_FRACTAL_K, S_R_ATR_MULT, S_R_PCT_TOL
            )
            if sr_d.get("support_level") is not None or sr_d.get("resistance_level") is not None:
                daily_block = {
                    "support": sr_d.get("support_level"),
                    "resistance": sr_d.get("resistance_level"),
                    "as_of": as_of,
                    "method": sr_d.get("method") or method,
                    "bar_count": len(daily_candles),
                    "tolerance_used": sr_d.get("tolerance_used"),
                    "supports_ordered": sr_d.get("supports_ordered") or [],
                    "resistances_ordered": sr_d.get("resistances_ordered") or [],
                }
        elif daily_block and daily_block.get("bar_count") is None and daily_candles:
            daily_block["bar_count"] = len(daily_candles)

        # Weekly: resample daily -> weekly, then S/R
        weekly_candles = _resample_daily_to_weekly(daily_candles)
        window_w = min(20, len(weekly_candles))
        if len(weekly_candles) >= min_bars and window_w >= min_bars:
            sr_w = compute_support_resistance(
                weekly_candles, float(spot), atr14, window_w, SWING_FRACTAL_K, S_R_ATR_MULT, S_R_PCT_TOL
            )
            weekly_block = {
                "support": sr_w.get("support_level"),
                "resistance": sr_w.get("resistance_level"),
                "as_of": as_of,
                "method": sr_w.get("method") or method,
                "bar_count": len(weekly_candles),
                "tolerance_used": sr_w.get("tolerance_used"),
                "supports_ordered": sr_w.get("supports_ordered") or [],
                "resistances_ordered": sr_w.get("resistances_ordered") or [],
            }
        else:
            weekly_block = _insufficient("weekly")

        # Monthly: resample daily -> monthly, then S/R
        monthly_candles = _resample_daily_to_monthly(daily_candles)
        window_m = min(24, len(monthly_candles))
        if len(monthly_candles) >= min_bars and window_m >= min_bars:
            sr_m = compute_support_resistance(
                monthly_candles, float(spot), atr14, window_m, SWING_FRACTAL_K, S_R_ATR_MULT, S_R_PCT_TOL
            )
            monthly_block = {
                "support": sr_m.get("support_level"),
                "resistance": sr_m.get("resistance_level"),
                "as_of": as_of,
                "method": sr_m.get("method") or method,
                "bar_count": len(monthly_candles),
                "tolerance_used": sr_m.get("tolerance_used"),
                "supports_ordered": sr_m.get("supports_ordered") or [],
                "resistances_ordered": sr_m.get("resistances_ordered") or [],
            }
        else:
            monthly_block = _insufficient("monthly")
    except Exception:
        weekly_block = weekly_block or _insufficient("weekly")
        monthly_block = monthly_block or _insufficient("monthly")

    return {
        "monthly": monthly_block,
        "weekly": weekly_block,
        "daily": daily_block,
        "4h": None,
    }


def _insufficient(timeframe: str) -> Dict[str, Any]:
    """Return INSUFFICIENT_HISTORY block for a timeframe (request-time only)."""
    return {"status_code": "INSUFFICIENT_HISTORY", "support": None, "resistance": None, "as_of": None, "method": None, "bar_count": None}


def _build_hold_time_estimate_at_request_time(
    technicals: Dict[str, Any],
    exit_plan: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """R22.4/R23.4.7: Hold-time estimate at request time. basis_key maps to display text. Not persisted.
    Returns hold_time_basis, hold_time_atr, hold_time_distance_to_t1, hold_time_sessions; nulls when unavailable."""
    t1 = exit_plan.get("t1")
    atr = technicals.get("atr")
    spot = technicals.get("spot") or 0
    if t1 is not None and atr is not None and float(atr) > 0:
        try:
            dist = abs(float(t1) - float(spot))
            if dist <= 0:
                return {
                    "sessions": 5,
                    "basis_key": "default_estimate",
                    "hold_time_basis": None,
                    "hold_time_atr": None,
                    "hold_time_distance_to_t1": None,
                    "hold_time_sessions": None,
                }
            sessions = max(1, int(round(dist / float(atr))))
            return {
                "sessions": sessions,
                "basis_key": "atr_sessions_to_target",
                "hold_time_basis": "ATR-based",
                "hold_time_atr": round(float(atr), 4),
                "hold_time_distance_to_t1": round(dist, 4),
                "hold_time_sessions": sessions,
            }
        except (TypeError, ValueError):
            pass
    return {
        "sessions": 5,
        "basis_key": "default_estimate",
        "hold_time_basis": None,
        "hold_time_atr": None,
        "hold_time_distance_to_t1": None,
        "hold_time_sessions": None,
    }


def _build_shares_plan_at_request_time(
    summary: Any,
    technicals: Dict[str, Any],
    exit_plan: Dict[str, Any],
    hold_time_estimate: Optional[Dict[str, Any]],
    symbol: str,
    mtf_levels: Optional[Dict[str, Any]] = None,
    as_of_inputs: Optional[Dict[str, Any]] = None,
    eligibility_codes: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """R22.5/R23.0: Shares plan at request time (recommendation only). Not persisted. Part D: eligible, eligibility_codes, spot, support_resistance, targets, hold_time, indicators_used, as_of_inputs."""
    regime = (technicals.get("regime") or getattr(summary, "regime", None) or "").upper()
    score = getattr(summary, "score", None) or getattr(summary, "final_score", None)
    support = technicals.get("support_level")
    resistance = technicals.get("resistance_level")
    codes = eligibility_codes or getattr(summary, "primary_reason_codes", None) or []
    if not codes and getattr(summary, "primary_reason", None):
        from app.core.eval.decision_artifact_v2 import _reason_string_to_codes
        codes = _reason_string_to_codes(getattr(summary, "primary_reason", None)) or []
    eligible = regime == "UP" and score is not None
    try:
        sup = float(support) if support is not None else None
        res = float(resistance) if resistance is not None else None
    except (TypeError, ValueError):
        sup, res = None, None
    if sup is None and res is None and not eligible:
        return None
    spot = technicals.get("spot") or (sup if sup is not None else res)
    try:
        spot = float(spot) if spot is not None else None
    except (TypeError, ValueError):
        spot = None
    band = 0.02
    entry_low = sup * (1 - band) if sup is not None else (spot * 0.98 if spot else None)
    entry_high = sup * (1 + band) if sup is not None else (spot * 1.02 if spot else None)
    stop = (sup * 0.97) if sup is not None else (spot * 0.95 if spot else None)
    t1, t2, t3 = exit_plan.get("t1"), exit_plan.get("t2"), exit_plan.get("t3")
    hold_time = hold_time_estimate or {"sessions": 5, "basis_key": "default_estimate"}
    support_resistance = {"daily": None, "weekly": None, "monthly": None}
    if mtf_levels:
        for tf in ("daily", "weekly", "monthly"):
            block = mtf_levels.get(tf)
            if block and isinstance(block, dict) and block.get("status_code") != "INSUFFICIENT_HISTORY":
                support_resistance[tf] = {"support": block.get("support"), "resistance": block.get("resistance"), "bar_count": block.get("bar_count"), "as_of": block.get("as_of"), "method": block.get("method")}
    indicators_used: Dict[str, Any] = {
        "rsi": technicals.get("rsi"),
        "atr": technicals.get("atr"),
        "regime": regime or None,
    }
    for k in ("ema20", "ema50", "ema200", "macd", "bbands"):
        if technicals.get(k) is not None:
            indicators_used[k] = technicals.get(k)
    return {
        "symbol": symbol,
        "eligible": eligible,
        "eligibility_codes": list(codes) if codes else [],
        "spot": round(spot, 2) if spot is not None else None,
        "support_resistance": support_resistance,
        "targets": {"t1": t1, "t2": t2, "t3": t3, "stop": stop, "invalidation": exit_plan.get("stop") or support},
        "hold_time": {"sessions_to_t1": hold_time.get("sessions"), "sessions_to_t2": None, "method": (hold_time.get("basis_key") or "default_estimate").upper().replace("-", "_")},
        "indicators_used": indicators_used,
        "as_of_inputs": as_of_inputs or {},
        "entry_zone": {"low": round(entry_low, 2) if entry_low is not None else None, "high": round(entry_high, 2) if entry_high is not None else None},
        "stop": round(stop, 2) if stop is not None else None,
        "invalidation": round(stop, 2) if stop is not None else None,
        "hold_time_estimate": hold_time,
        "confidence_score": int(score) if score is not None else None,
        "why_recommended": "MTF_SUPPORT_REGIME_UP" if eligible else None,
    }


def _build_delta_diagnostics_at_request_time(
    sample_rejected_due_to_delta: List[Dict[str, Any]],
    delta_lo: float,
    delta_hi: float,
) -> Optional[Dict[str, Any]]:
    """R23.1: Request-time only. When rejected due to delta, return best_delta, miss, direction, best_candidate. Not persisted."""
    if not sample_rejected_due_to_delta or delta_lo >= delta_hi:
        return None
    best_sample: Optional[Dict[str, Any]] = None
    best_miss: Optional[float] = None
    for s in sample_rejected_due_to_delta:
        d_abs = s.get("observed_delta_decimal_abs")
        if d_abs is None:
            d_abs = s.get("observed_delta_decimal_raw")
        if d_abs is None:
            continue
        try:
            d_val = float(d_abs)
        except (TypeError, ValueError):
            continue
        if d_val < delta_lo:
            miss = delta_lo - d_val
            direction = "BELOW_BAND"
        elif d_val > delta_hi:
            miss = d_val - delta_hi
            direction = "ABOVE_BAND"
        else:
            miss = 0.0
            direction = "IN_BAND"
        if best_miss is None or miss < best_miss:
            best_miss = miss
            best_sample = {
                "band_min": delta_lo,
                "band_max": delta_hi,
                "best_delta": round(d_val, 4),
                "miss": round(miss, 4),
                "direction": direction,
                "best_candidate": {
                    "strike": s.get("strike"),
                    "expiry": s.get("expiry"),
                    "dte": s.get("dte"),
                    "bid": s.get("bid"),
                    "ask": s.get("ask"),
                    "spread": s.get("spread_pct"),
                    "contract_key": s.get("contract_key"),
                    "option_symbol": s.get("option_symbol"),
                },
            }
    return best_sample


def _build_computed_values_at_request_time(
    technicals: Dict[str, Any],
    regime: Any,
    sample_rejected_due_to_delta: List[Any],
) -> Dict[str, Any]:
    """Build computed_values at request time for R21.4 Technical details panel. Not persisted."""
    try:
        from app.core.config.trade_rules import CSP_TARGET_DELTA_LOW, CSP_TARGET_DELTA_HIGH
        delta_lo, delta_hi = float(CSP_TARGET_DELTA_LOW), float(CSP_TARGET_DELTA_HIGH)
    except Exception:
        delta_lo, delta_hi = 0.25, 0.35
    try:
        from app.core.eligibility.config import CSP_RSI_MIN, CSP_RSI_MAX
        rsi_lo, rsi_hi = float(CSP_RSI_MIN), float(CSP_RSI_MAX)
    except Exception:
        rsi_lo, rsi_hi = 45.0, 60.0
    rejected_sample = list(sample_rejected_due_to_delta) if sample_rejected_due_to_delta else []
    return {
        "rsi": technicals.get("rsi"),
        "rsi_range": [rsi_lo, rsi_hi],
        "atr": technicals.get("atr"),
        "atr_pct": technicals.get("atr_pct"),
        "support_level": technicals.get("support_level"),
        "resistance_level": technicals.get("resistance_level"),
        "regime": regime,
        "delta_band": [delta_lo, delta_hi],
        "rejected_count": len(rejected_sample),
    }


def _config_hash_for_diagnostics() -> str:
    """R22.7: Stable hash of key eval config for As-of/Inputs fingerprint (request-time only)."""
    try:
        import hashlib
        from app.core.scoring.config import TIER_A_MIN, TIER_B_MIN, TIER_C_MIN
        blob = f"TIER_A={TIER_A_MIN}_B={TIER_B_MIN}_C={TIER_C_MIN}"
        return hashlib.sha256(blob.encode()).hexdigest()[:12]
    except Exception:
        return ""


def _build_technicals_at_request_time(symbol: str, spot: Optional[float]) -> Dict[str, Any]:
    """
    R23.4.4: Rebuild technicals at request time when diagnostics not persisted.
    Uses eligibility engine (same as evaluation); returns only non-null values so UI does not show dashes for missing.
    """
    if not (symbol or "").strip():
        return {}
    try:
        from app.core.eligibility.eligibility_engine import run as eligibility_run
        _mode, trace = eligibility_run(
            (symbol or "").strip().upper(),
            holdings=None,
            current_price=spot,
            lookback=255,
        )
    except Exception:
        return {}
    computed = (trace or {}).get("computed") or {}
    regime = (trace or {}).get("regime")
    rsi = computed.get("RSI14") if computed.get("RSI14") is not None else computed.get("rsi14")
    atr = computed.get("ATR14") if computed.get("ATR14") is not None else computed.get("atr14")
    atr_pct = computed.get("ATR_pct") if computed.get("ATR_pct") is not None else computed.get("atr_pct")
    support_level = computed.get("support_level")
    resistance_level = computed.get("resistance_level")
    out: Dict[str, Any] = {}
    if rsi is not None:
        out["rsi"] = round(float(rsi), 2)
    if atr is not None:
        out["atr"] = round(float(atr), 4)
    if atr_pct is not None:
        out["atr_pct"] = round(float(atr_pct), 4)
    if support_level is not None:
        out["support_level"] = round(float(support_level), 4)
    if resistance_level is not None:
        out["resistance_level"] = round(float(resistance_level), 4)
    if regime:
        out["regime"] = str(regime).strip().upper()
    if spot is not None:
        out["spot"] = round(float(spot), 2)
    return out


def _build_symbol_diagnostics_from_v2_store(
    summary: Any,
    candidates: List[Any],
    gates: List[Any],
    earnings: Any | None,
    diagnostics_details: Any | None,
    symbol: str,
    selected_contract_key: Optional[str] = None,
    option_symbol: Optional[str] = None,
    pipeline_timestamp: Optional[str] = None,
    run_id: Optional[str] = None,
    eval_snapshot: Optional[Dict[str, Any]] = None,
    shares_position: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build full SymbolDiagnosticsResponseExtended from v2 store (summary + candidates + gates + earnings + diagnostics_details)."""
    c_dicts = [c.to_dict() if hasattr(c, "to_dict") else (c if isinstance(c, dict) else {}) for c in candidates]
    from app.core.eval.reason_codes import format_reason_for_display
    from app.core.eval.decision_artifact_v2 import gate_code_to_label, gate_name_to_code
    g_list = [
        {
            "name": gate_code_to_label(getattr(g, "gate_code", None)) or gate_code_to_label(gate_name_to_code(g.name)) or (g.name or "Gate"),
            "status": g.status,
            "reason": format_reason_for_display(g.reason) or (g.reason or ""),
            "pass": g.status == "PASS",
        }
        for g in (gates or [])
    ]
    diag = diagnostics_details
    if diag and hasattr(diag, "to_dict"):
        diag = diag.to_dict()
    diag = diag or {}
    technicals = diag.get("technicals") or {}
    exit_plan = diag.get("exit_plan") or {}
    risk_flags = diag.get("risk_flags") or {}
    explanation = diag.get("explanation") or {}
    stock = diag.get("stock") or {}
    # When diagnostics not persisted (store load), derive minimal stock from summary so UI can show price
    if not stock and summary:
        price_val = getattr(summary, "price", None) or getattr(summary, "underlying_price", None)
        if price_val is not None:
            p = float(price_val)
            stock = {
                "price": p,
                "underlying_price": p,
                "quote_as_of": getattr(summary, "data_freshness", None),
            }
    # R23.4.4: When technicals missing (e.g. store load), rebuild at request time from eligibility engine
    spot_for_tech = stock.get("price") or stock.get("underlying_price") if stock else None
    if spot_for_tech is None and summary:
        spot_for_tech = getattr(summary, "price", None) or getattr(summary, "underlying_price", None)
    # R25.3: EOD_BIASED — use last completed daily candle close for eligibility so it doesn't flip intraday
    eligibility_as_of_ts: Optional[str] = None
    cadence_mode = "LIVE"
    try:
        from app.core.settings import get_decision_cadence_mode
        cadence_mode = get_decision_cadence_mode()
        if cadence_mode == "EOD_BIASED" and (symbol or "").strip():
            from app.core.eligibility.candles import get_candles
            daily_candles = get_candles((symbol or "").strip().upper(), "daily", 30)
            if daily_candles and len(daily_candles) >= 1:
                last_bar = daily_candles[-1]
                if isinstance(last_bar, dict):
                    close_val = last_bar.get("close") or last_bar.get("c")
                    if close_val is not None:
                        spot_for_tech = float(close_val)
                        eligibility_as_of_ts = last_bar.get("ts") or last_bar.get("date") or last_bar.get("t") or last_bar.get("timestamp")
                        if eligibility_as_of_ts is not None and not isinstance(eligibility_as_of_ts, str):
                            eligibility_as_of_ts = str(eligibility_as_of_ts)
                elif hasattr(last_bar, "close"):
                    spot_for_tech = float(last_bar.close)
                    eligibility_as_of_ts = getattr(last_bar, "ts", None) or getattr(last_bar, "date", None) or getattr(last_bar, "t", None)
                    if eligibility_as_of_ts is not None:
                        eligibility_as_of_ts = str(eligibility_as_of_ts)
    except Exception:
        pass
    # R25.8: eligibility_is_intraday_stale — True when EOD_BIASED and last bar date (ET) < today (ET)
    eligibility_is_intraday_stale: bool = False
    if cadence_mode == "EOD_BIASED" and eligibility_as_of_ts:
        try:
            import zoneinfo
            ny = zoneinfo.ZoneInfo("America/New_York")
        except ImportError:
            try:
                from backports.zoneinfo import ZoneInfo
                ny = ZoneInfo("America/New_York")
            except ImportError:
                ny = None
        if ny:
            now_et = datetime.now(ny).date()
            ts_str = str(eligibility_as_of_ts)[:10]
            if len(ts_str) == 10 and ts_str[4] == "-":
                bar_date = datetime.strptime(ts_str, "%Y-%m-%d").date()
                eligibility_is_intraday_stale = bar_date < now_et
    if not technicals and symbol and spot_for_tech is not None:
        technicals = _build_technicals_at_request_time(symbol, float(spot_for_tech))
    if not technicals and symbol:
        technicals = _build_technicals_at_request_time(symbol, None)
    mtf_levels_early: Optional[Dict[str, Any]] = None
    if technicals and (exit_plan.get("t1") is None and exit_plan.get("t2") is None and exit_plan.get("stop") is None):
        try:
            from app.core.lifecycle.exit_planner import build_exit_plan_v235
            from app.core.config.trade_rules import MIN_TARGET_DISTANCE_PCT, TARGET_EPS_PCT
            spot_ep = float(technicals.get("spot") or spot_for_tech or 0)
            atr_ep = technicals.get("atr")
            mtf_levels_early = _build_mtf_levels_at_request_time(symbol, technicals, {}, pipeline_timestamp)
            resistances_by_tf = {
                tf: (mtf_levels_early.get(tf) or {}).get("resistances_ordered") or []
                for tf in ("daily", "weekly", "monthly")
            }
            supports_by_tf = {
                tf: (mtf_levels_early.get(tf) or {}).get("supports_ordered") or []
                for tf in ("daily", "weekly", "monthly")
            }
            ep_result = build_exit_plan_v235(
                spot_ep, "CSP", atr_ep, resistances_by_tf, supports_by_tf,
                min_distance_pct=MIN_TARGET_DISTANCE_PCT, eps_pct=TARGET_EPS_PCT,
            )
            sp = (ep_result.get("structure_plan") or {}) if isinstance(ep_result, dict) else {}
            if sp and (sp.get("T1") is not None or sp.get("stop_hint_price") is not None):
                exit_plan = {
                    "t1": sp.get("T1"),
                    "t2": sp.get("T2"),
                    "t3": sp.get("T3"),
                    "stop": sp.get("stop_hint_price"),
                    "status": "AVAILABLE",
                    "reason": None,
                    "target_basis": ep_result.get("target_basis"),
                    "level_source_timeframe": ep_result.get("level_source_timeframe"),
                    "distance_to_t1_pct": ep_result.get("distance_to_t1_pct"),
                }
                if ep_result.get("support_level") is not None or ep_result.get("resistance_level") is not None:
                    technicals = dict(technicals)
                    if ep_result.get("support_level") is not None:
                        technicals["support_level"] = ep_result.get("support_level")
                    if ep_result.get("resistance_level") is not None:
                        technicals["resistance_level"] = ep_result.get("resistance_level")
                t1_val = sp.get("T1")
                if t1_val is not None and spot_ep and spot_ep >= float(t1_val):
                    exit_plan["targets_already_exceeded"] = True
            elif not exit_plan:
                exit_plan = {"status": "NOT_AVAILABLE", "reason": "Missing inputs (support_level, resistance_level, or ATR)."}
        except Exception:
            pass
    symbol_eligibility = diag.get("symbol_eligibility") or {}
    liquidity = diag.get("liquidity") or {}
    earnings_out = None
    if earnings:
        note = getattr(earnings, "note", None)
        if not note and getattr(earnings, "status_code", None):
            sc = (earnings.status_code or "").strip()
            if sc == "EARNINGS_NOT_EVALUATED":
                note = "Unavailable"
            elif sc == "EARNINGS_BLOCKED":
                note = "Earnings block"
            elif sc == "EARNINGS_OK":
                note = None
            else:
                note = "Unavailable"
        earnings_out = {
            "earnings_days": getattr(earnings, "earnings_days", None),
            "earnings_block": getattr(earnings, "earnings_block", None),
            "note": note or "Unavailable",
            "earnings_next_date": None,
            "earnings_annc_tod": "Unknown",
            "implied_earnings_move_pct": None,
            "earnings_data_status": "Unavailable",
            "earnings_as_of": None,
        }
        # R24.5: Merge snapshot earnings advisory (request-time only; never FAIL_/WARN_)
        sym_upper = (symbol or "").strip().upper()
        if eval_snapshot and sym_upper:
            snap_earnings = (eval_snapshot.get("earnings_by_symbol") or {}).get(sym_upper)
            if isinstance(snap_earnings, dict):
                earnings_out["earnings_next_date"] = snap_earnings.get("earnings_next_date")
                if snap_earnings.get("earnings_days") is not None:
                    earnings_out["earnings_days"] = snap_earnings.get("earnings_days")
                earnings_out["earnings_annc_tod"] = snap_earnings.get("earnings_annc_tod", "Unknown")
                earnings_out["implied_earnings_move_pct"] = snap_earnings.get("implied_earnings_move_pct")
                earnings_out["earnings_data_status"] = snap_earnings.get("earnings_data_status", "Unavailable")
                earnings_out["earnings_as_of"] = snap_earnings.get("earnings_as_of")
                if snap_earnings.get("earnings_data_status") != "OK":
                    earnings_out["note"] = earnings_out.get("note") or "Unavailable"
    regime = diag.get("regime") or getattr(summary, "regime", None) or technicals.get("regime")
    sample_rej = diag.get("sample_rejected_due_to_delta") or []
    # R23.4.4: Minimal explanation from regime when not persisted (so candidate table can show regime)
    if not explanation and regime:
        explanation = {"stock_regime_reason": str(regime)}
    if isinstance(explanation, dict):
        if regime and not explanation.get("stock_regime_reason"):
            explanation = dict(explanation)
            explanation["stock_regime_reason"] = str(regime)
        sup = technicals.get("support_level")
        res = technicals.get("resistance_level")
        if sup is not None and not explanation.get("support_condition"):
            explanation = dict(explanation)
            explanation["support_condition"] = f"Support ${float(sup):.2f}"
        if res is not None and not explanation.get("resistance_condition"):
            explanation = dict(explanation)
            explanation["resistance_condition"] = f"Resistance ${float(res):.2f}"
    # R23.4.4: When sample not persisted, use summary count so rejected_count is not zero when we have a count
    rejected_count_from_summary = getattr(summary, "rejected_due_to_delta_count", None)
    computed_values = _build_computed_values_at_request_time(technicals, regime, sample_rej)
    if rejected_count_from_summary is not None and isinstance(rejected_count_from_summary, int) and computed_values.get("rejected_count") == 0 and rejected_count_from_summary > 0:
        computed_values["rejected_count"] = rejected_count_from_summary
    try:
        from app.core.config.trade_rules import CSP_TARGET_DELTA_LOW, CSP_TARGET_DELTA_HIGH
        _dlo, _dhi = float(CSP_TARGET_DELTA_LOW), float(CSP_TARGET_DELTA_HIGH)
    except Exception:
        _dlo, _dhi = 0.25, 0.35
    delta_diagnostics = _build_delta_diagnostics_at_request_time(sample_rej, _dlo, _dhi)
    mtf_levels = mtf_levels_early if mtf_levels_early is not None else _build_mtf_levels_at_request_time(symbol, technicals, exit_plan, pipeline_timestamp)
    methodology = {
        "candles_source": "diagnostics",
        "window": "20",
        "clustering_tolerance_pct": 1.0,
        "active_criteria": "nearest_to_spot",
    }
    targets = {
        "t1": exit_plan.get("t1"),
        "t2": exit_plan.get("t2"),
        "t3": exit_plan.get("t3"),
        "target_basis": exit_plan.get("target_basis"),
        "level_source_timeframe": exit_plan.get("level_source_timeframe"),
        "distance_to_t1_pct": exit_plan.get("distance_to_t1_pct"),
        "targets_already_exceeded": exit_plan.get("targets_already_exceeded"),
    }
    invalidation = exit_plan.get("stop") or technicals.get("support_level")
    hold_time_estimate = _build_hold_time_estimate_at_request_time(technicals, exit_plan)
    quote_as_of = stock.get("quote_as_of") or getattr(summary, "data_freshness", None)
    as_of_inputs = {
        "evaluation_run_id": run_id,
        "pipeline_timestamp": pipeline_timestamp,
        "quote_as_of": quote_as_of,
        "candles_as_of": pipeline_timestamp,
        "orats_as_of": quote_as_of,
        "config_hash": _config_hash_for_diagnostics(),
    }
    if eval_snapshot:
        as_of_inputs["snapshot_id"] = eval_snapshot.get("snapshot_id")
        as_of_inputs["snapshot_created_at"] = eval_snapshot.get("created_at")
        if eval_snapshot.get("quote_as_of") is not None:
            as_of_inputs["quote_as_of"] = eval_snapshot.get("quote_as_of")
        if eval_snapshot.get("candles_as_of") is not None:
            as_of_inputs["candles_as_of"] = eval_snapshot.get("candles_as_of")
        if eval_snapshot.get("orats_as_of") is not None:
            as_of_inputs["orats_as_of"] = eval_snapshot.get("orats_as_of")
    # R23.3: Shares plan (eligibility + plan + sizing) — request-time only, not persisted
    account_summary = None
    try:
        from app.core.accounts.holdings_db import get_account_summary
        account_summary = get_account_summary()
        from app.core.accounts.service import get_default_account
        default_acc = get_default_account()
        if default_acc and getattr(default_acc, "total_capital", None) is not None:
            account_summary = dict(account_summary or {})
            account_summary["total_capital"] = default_acc.total_capital
    except Exception:
        pass
    from app.core.shares.shares_plan import build_shares_plan_r233
    shares_plan = build_shares_plan_r233(
        summary, technicals, exit_plan, hold_time_estimate, symbol,
        mtf_levels=mtf_levels, as_of_inputs=as_of_inputs,
        symbol_eligibility=symbol_eligibility,
        account_summary=account_summary,
    )
    # R23.2: Include delta_override for this symbol when present (for UI "Override active" badge and advanced form)
    delta_override = None
    try:
        from app.core.config.delta_overrides import load_delta_overrides
        overrides = load_delta_overrides()
        sym_upper = (symbol or "").strip().upper()
        if sym_upper in overrides:
            delta_override = overrides[sym_upper]
    except Exception:
        pass
    # R24.0: Options sizing (request-time only; never persisted)
    spot_for_sizing = None
    if stock:
        spot_for_sizing = stock.get("price") or stock.get("underlying_price")
    if spot_for_sizing is None and summary:
        spot_for_sizing = getattr(summary, "price", None) or getattr(summary, "underlying_price", None)
    from app.core.options.options_sizing import build_options_sizing_r240
    options_sizing = build_options_sizing_r240(
        c_dicts,
        selected_contract_key,
        getattr(summary, "strategy", None),
        account_summary,
        shares_position,
        float(spot_for_sizing) if spot_for_sizing is not None else None,
    )
    # R24.1: next_action_code + next_action_details (request-time only; never persisted)
    next_action_code = "NONE"
    next_action_details: Dict[str, Any] = {}
    # R25.2: shares exit signal (request-time only; never persisted)
    shares_exit_hit_type: Optional[str] = None
    shares_exit_target_price: Optional[float] = None
    shares_exit_stop_price: Optional[float] = None
    shares_exit_last_price: Optional[float] = None
    shares_exit_as_of_ts: Optional[str] = None
    shares_exit_reason_safe: Optional[str] = None
    try:
        from app.core.positions.service import list_positions
        from app.core.next_action_r241 import (
            compute_next_action_options,
            compute_next_action_shares,
            build_next_action_details,
            compute_shares_exit_signal,
        )
        open_positions = list_positions(status="OPEN", symbol=(symbol or "").strip().upper(), exclude_test=True)
        open_options = [p for p in open_positions if (getattr(p, "strategy", "") or "").upper() in ("CSP", "CC")]
        has_open_option = len(open_options) > 0
        has_shares_position = shares_position is not None
        if shares_plan is None:
            shares_eligible = False
        elif isinstance(shares_plan, dict):
            shares_eligible = bool(shares_plan.get("eligible"))
        else:
            shares_eligible = bool(getattr(shares_plan, "eligible", False))
        spot_float = float(spot_for_sizing) if spot_for_sizing is not None else None
        # R25.2: shares exit signal from position-level target/stop (request-time only; never persisted)
        if has_shares_position and isinstance(shares_position, dict) and spot_float is not None:
            pos_tgt = shares_position.get("target_price") if isinstance(shares_position.get("target_price"), (int, float)) else None
            pos_stop = shares_position.get("stop_price") if isinstance(shares_position.get("stop_price"), (int, float)) else None
            if pos_tgt is not None or pos_stop is not None:
                hit_type, reason_safe = compute_shares_exit_signal(last_price=spot_float, target_price=pos_tgt, stop_price=pos_stop)
                shares_exit_target_price = float(pos_tgt) if pos_tgt is not None else None
                shares_exit_stop_price = float(pos_stop) if pos_stop is not None else None
                shares_exit_last_price = spot_float
                shares_exit_as_of_ts = datetime.now(timezone.utc).isoformat()
                shares_exit_reason_safe = reason_safe or None
                shares_exit_hit_type = hit_type
                if hit_type in ("TARGET", "STOP"):
                    try:
                        from app.api.notifications_store import maybe_append_shares_exit_notification
                        maybe_append_shares_exit_notification(
                            symbol=(symbol or "").strip().upper(),
                            hit_type=hit_type,
                            last_price=spot_float,
                            target_price=shares_exit_target_price,
                            stop_price=shares_exit_stop_price,
                            as_of_ts=shares_exit_as_of_ts,
                        )
                    except Exception:
                        pass
        # Selected candidate delta/dte for options
        delta_best = None
        dte_val = None
        for c in c_dicts:
            if c.get("contract_key") == selected_contract_key:
                delta_best = c.get("delta")
                dte_val = c.get("dte")
                break
        code_opt, rationale_opt, key_opt = compute_next_action_options(
            has_open_option=has_open_option,
            selected_contract_key=selected_contract_key,
            exit_plan=exit_plan,
            spot=spot_float,
            delta_best=delta_best,
            dte=dte_val,
            strategy=getattr(summary, "strategy", None),
        )
        ep_for_shares = {"t1": exit_plan.get("t1"), "stop": exit_plan.get("stop"), "targets_already_exceeded": exit_plan.get("targets_already_exceeded")}
        plan_dict = shares_plan.to_dict() if hasattr(shares_plan, "to_dict") else (shares_plan if isinstance(shares_plan, dict) else {})
        code_shares, rationale_shares, key_shares = compute_next_action_shares(
            shares_eligible=shares_eligible,
            has_shares_position=has_shares_position,
            shares_plan=plan_dict,
            exit_plan_or_targets=ep_for_shares,
            spot=spot_float,
        )
        # Primary: options if we have option context else shares
        if has_open_option or selected_contract_key:
            next_action_code = code_opt
            premium_est = None
            if options_sizing and isinstance(options_sizing, dict):
                premium_est = options_sizing.get("credit_estimate")
            next_action_details = build_next_action_details(
                "OPTIONS", code_opt, rationale_opt, key_opt,
                option_symbol=option_symbol,
                contract_key=selected_contract_key,
                premium_est=premium_est,
            )
        else:
            # R25.2: position-level target/stop hit overrides plan-based next_action
            if shares_exit_hit_type in ("TARGET", "STOP") and shares_exit_reason_safe:
                next_action_code = "CLOSE"
                next_action_details = build_next_action_details(
                    "SHARES", "CLOSE", [shares_exit_reason_safe], key_shares or {"spot": spot_float},
                )
            else:
                next_action_code = code_shares
                next_action_details = build_next_action_details("SHARES", code_shares, rationale_shares, key_shares)
    except Exception:
        pass
    return {
        "symbol": symbol,
        "provider_status": getattr(summary, "provider_status", "OK") or "OK",
        "provider_message": "",
        "primary_reason": _primary_reason_display(summary),
        "as_of_inputs": as_of_inputs,
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
        "computed_values": computed_values,
        "regime": regime,
        "composite_score": getattr(summary, "score", None),
        "raw_score": getattr(summary, "raw_score", None),
        "final_score": getattr(summary, "final_score", None) or getattr(summary, "score", None),
        "pre_cap_score": getattr(summary, "pre_cap_score", None) or getattr(summary, "raw_score", None),
        "score_caps": getattr(summary, "score_caps", None),
        "confidence_band": getattr(summary, "band", "D"),
        "suggested_capital_pct": diag.get("suggested_capital_pct"),
        "band_reason": getattr(summary, "band_reason", None),
        "candidates": c_dicts,
        "exit_plan": {
            "t1": exit_plan.get("t1"),
            "t2": exit_plan.get("t2"),
            "t3": exit_plan.get("t3"),
            "stop": exit_plan.get("stop"),
            "status": exit_plan.get("status"),
            "reason": exit_plan.get("reason"),
            "target_basis": exit_plan.get("target_basis"),
            "level_source_timeframe": exit_plan.get("level_source_timeframe"),
            "distance_to_t1_pct": exit_plan.get("distance_to_t1_pct"),
            "targets_already_exceeded": exit_plan.get("targets_already_exceeded"),
        },
        "score_breakdown": diag.get("score_breakdown") or getattr(summary, "score_breakdown", None),
        "rank_reasons": diag.get("rank_reasons"),
        "reasons_explained": _compute_reasons_explained(
            getattr(summary, "primary_reason", None) or "",
            symbol_eligibility,
            diag.get("sample_rejected_due_to_delta") or [],
        ),
        "sample_rejected_due_to_delta": diag.get("sample_rejected_due_to_delta") or [],
        "delta_diagnostics": delta_diagnostics,
        "delta_override": delta_override,
        "earnings": earnings_out,
        "selected_contract_key": selected_contract_key,
        "option_symbol": option_symbol,
        "mtf_levels": mtf_levels,
        "methodology": methodology,
        "targets": targets,
        "invalidation": invalidation,
        "hold_time_estimate": hold_time_estimate,
        "shares_plan": shares_plan,
        "shares_position": shares_position,
        "options_sizing": options_sizing,
        "next_action_code": next_action_code,
        "next_action_details": next_action_details,
        # R25.2: request-time only; never persisted to decision artifact
        "shares_exit_hit_type": shares_exit_hit_type,
        "shares_exit_target_price": shares_exit_target_price,
        "shares_exit_stop_price": shares_exit_stop_price,
        "shares_exit_last_price": shares_exit_last_price,
        "shares_exit_as_of_ts": shares_exit_as_of_ts,
        "shares_exit_reason_safe": shares_exit_reason_safe,
        # R25.3/R25.8: EOD_BIASED eligibility; request-time only
        "cadence_mode": cadence_mode,
        "eligibility_as_of_ts": eligibility_as_of_ts,
        "eligibility_is_intraday_stale": eligibility_is_intraday_stale,
    }


def _action_needed_item_from_diagnostics(d: Dict[str, Any], strategy: str) -> Dict[str, Any]:
    """R24.1/R24.2: Extract action-needed row from full diagnostics. Includes tab + accordion id, severity, lifecycle fields."""
    from app.core.next_action_r241 import lifecycle_severity, lifecycle_recommended_by
    details = d.get("next_action_details") or {}
    rationale = details.get("rationale_lines") or []
    key_num = details.get("key_numbers") or {}
    code = d.get("next_action_code") or "NONE"
    symbol = d.get("symbol") or ""
    tab = "Options" if strategy == "OPTIONS" else "Shares"
    accordion = "Trade" if strategy == "OPTIONS" else "Trade Plan"
    accordion_id = "trade" if strategy == "OPTIONS" else "trade-plan"
    key_number_label = None
    key_number_value = None
    if key_num.get("delta_best") is not None:
        key_number_label = "delta"
        key_number_value = key_num["delta_best"]
    elif key_num.get("spot") is not None:
        key_number_label = "spot"
        key_number_value = key_num["spot"]
    key_display = None
    if key_number_label and key_number_value is not None:
        key_display = "%s %s" % (key_number_label, _fmt_num(key_number_value) if key_number_label == "delta" else str(key_number_value))
    severity = lifecycle_severity(code)
    recommended_by = lifecycle_recommended_by()
    out: Dict[str, Any] = {
        "symbol": symbol,
        "strategy": strategy,
        "next_action_code": code,
        "rationale_lines": rationale[:2],
        "key_number": key_display,
        "key_number_label": key_number_label,
        "key_number_value": key_number_value,
        "tab": tab,
        "accordion": accordion,
        "accordion_id": accordion_id,
        "severity": severity,
        "recommended_by": recommended_by,
    }
    if strategy == "OPTIONS":
        sel_key = d.get("selected_contract_key")
        candidates = d.get("candidates") or []
        sel_c = None
        for c in candidates:
            if isinstance(c, dict) and c.get("contract_key") == sel_key:
                sel_c = c
                break
        if sel_c is None and candidates:
            sel_c = candidates[0] if isinstance(candidates[0], dict) else None
        if sel_c:
            if sel_c.get("expiry") is not None:
                out["expiry"] = sel_c["expiry"]
            if sel_c.get("strike") is not None:
                out["strike"] = sel_c["strike"]
            if sel_c.get("dte") is not None:
                out["dte"] = sel_c["dte"]
        sizing = d.get("options_sizing") or {}
        if sizing.get("suggested_contracts") is not None:
            out["size"] = sizing["suggested_contracts"]
        if sizing.get("required_cash") is not None:
            out["notional"] = sizing["required_cash"]
        if key_num.get("profit_pct") is not None:
            out["pct_max_profit"] = key_num["profit_pct"]
    if strategy == "SHARES":
        # R25.2: surface shares exit signal for Action Needed (safe labels only)
        if d.get("shares_exit_hit_type") is not None:
            out["shares_exit_hit_type"] = d["shares_exit_hit_type"]
        if d.get("shares_exit_reason_safe") is not None:
            out["shares_exit_reason_safe"] = d["shares_exit_reason_safe"]
        if d.get("shares_exit_last_price") is not None:
            out["shares_exit_last_price"] = d["shares_exit_last_price"]
        if d.get("shares_exit_target_price") is not None:
            out["shares_exit_target_price"] = d["shares_exit_target_price"]
        if d.get("shares_exit_stop_price") is not None:
            out["shares_exit_stop_price"] = d["shares_exit_stop_price"]
        if d.get("shares_exit_as_of_ts") is not None:
            out["shares_exit_as_of_ts"] = d["shares_exit_as_of_ts"]
    return out


def _fmt_num(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        return "%.2f" % f if f != int(f) else str(int(f))
    except (TypeError, ValueError):
        return str(v) if v is not None else "—"


@router.get("/action-needed")
def ui_action_needed(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R24.1: Top 5 options + top 5 shares actions; recently changed (last 5 transitions). For Dashboard workflow."""
    _require_ui_key(x_ui_key)
    from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2, get_eval_snapshot
    from app.core.accounts.holdings_db import get_share_position, _DEFAULT_ACCOUNT_ID
    from app.core.next_action_r241 import _recent_transitions

    store = get_evaluation_store_v2()
    store.reload_from_disk()
    artifact = store.get_latest()
    if artifact is None:
        return {"options": [], "shares": [], "recently_changed": _recent_transitions()}

    # R25.9: Guardrails — compute metrics once for request-time ENTRY suppression
    # R26.0: Sizing uses same snapshot + metrics for portfolio-aware size
    guardrails_metrics: Dict[str, Any] = {}
    guardrails_snapshot: Dict[str, Any] = {}
    try:
        from app.core.portfolio.guardrails_r259 import (
            build_guardrails_snapshot,
            compute_portfolio_metrics,
            evaluate_guardrails_for_entry,
        )
        _guard_snap = build_guardrails_snapshot()
        guardrails_snapshot = dict(_guard_snap)
        _snap_for_prices = get_eval_snapshot()
        _prices = {}
        if _snap_for_prices and isinstance(_snap_for_prices, dict):
            for _sym, _v in (_snap_for_prices.get("symbols") or {}).items():
                if isinstance(_v, dict) and _v.get("price") is not None:
                    _prices[_sym] = float(_v["price"])
        guardrails_metrics = compute_portfolio_metrics(_guard_snap, symbol_prices=_prices)
        guardrails_snapshot["total_equity"] = guardrails_metrics.get("total_equity")
        guardrails_snapshot["symbol_notionals"] = guardrails_metrics.get("symbol_notionals") or {}
    except Exception:
        pass

    option_symbols: List[str] = []
    for c in (getattr(artifact, "selected_candidates", []) or [])[:5]:
        sym = (getattr(c, "symbol", "") or "").strip().upper()
        if sym and sym not in option_symbols:
            option_symbols.append(sym)

    symbols = getattr(artifact, "symbols", []) or []
    diag_by = getattr(artifact, "diagnostics_by_symbol", {}) or {}
    share_plans: List[tuple[str, Any]] = []
    for s in symbols:
        sym = (getattr(s, "symbol", "") or "").strip().upper()
        if not sym:
            continue
        diag = diag_by.get(sym)
        if diag is None:
            continue
        diag = diag.to_dict() if hasattr(diag, "to_dict") else (diag if isinstance(diag, dict) else {})
        technicals = diag.get("technicals") or {}
        exit_plan = diag.get("exit_plan") or {}
        hold_time = _build_hold_time_estimate_at_request_time(technicals, exit_plan)
        plan = _build_shares_plan_at_request_time(s, technicals, exit_plan, hold_time, sym)
        if plan is not None:
            share_plans.append((sym, plan))
    share_symbols = [sym for sym, _ in share_plans[:5]]

    options_out: List[Dict[str, Any]] = []
    for sym in option_symbols:
        row = store.get_symbol(sym)
        if row is None:
            continue
        summary, candidates, gates, earnings, diagnostics_details = row
        sel_c = next((c for c in (getattr(artifact, "selected_candidates", []) or []) if (getattr(c, "symbol", "") or "").strip().upper() == sym), None)
        _sel_key = getattr(sel_c, "contract_key", None) if sel_c else None
        _opt_sym = getattr(sel_c, "option_symbol", None) if sel_c else None
        _snap = get_eval_snapshot()
        _share_pos = get_share_position(_DEFAULT_ACCOUNT_ID, sym)
        try:
            diag = _build_symbol_diagnostics_from_v2_store(
                summary, candidates, gates, earnings, diagnostics_details, sym,
                selected_contract_key=_sel_key, option_symbol=_opt_sym,
                pipeline_timestamp=(artifact.metadata or {}).get("pipeline_timestamp") if artifact else None,
                run_id=(artifact.metadata or {}).get("run_id") if artifact else None,
                eval_snapshot=_snap,
                shares_position=_share_pos,
            )
            item = _action_needed_item_from_diagnostics(diag, "OPTIONS")
            # R24.3/R24.4: Enrich with position lifecycle for tracked option positions (request-time only)
            try:
                import time as _time
                from app.core.positions.service import list_positions
                from app.core.positions.quote_resolver import find_contract_quote
                from app.core.lifecycle.position_lifecycle_r243 import (
                    compute_position_lifecycle,
                    RECOMMENDED_BY_R253,
                )
                open_pos = list_positions(status="OPEN", symbol=sym, exclude_test=True)
                opt_positions = [p for p in open_pos if (getattr(p, "strategy", "") or "").upper() in ("CSP", "CC")]
                if opt_positions:
                    spot_for_lifecycle = None
                    stock = diag.get("stock") or {}
                    if isinstance(stock, dict) and stock.get("price") is not None:
                        spot_for_lifecycle = float(stock["price"])
                    if spot_for_lifecycle is None and getattr(summary, "price", None) is not None:
                        spot_for_lifecycle = float(summary.price)
                    pos = opt_positions[0]
                    chain_rows = diag.get("candidates") or []
                    expiry = getattr(pos, "expiration", None) or getattr(pos, "expiry", None)
                    strike = getattr(pos, "strike", None)
                    quote = find_contract_quote(chain_rows, expiry, strike, "PUT") if chain_rows and expiry and strike is not None else None
                    quote_ts = None
                    if quote and quote.get("quote_ts"):
                        quote_ts = str(quote["quote_ts"])
                    elif _snap and isinstance(_snap, dict):
                        syms = _snap.get("symbols") or {}
                        if isinstance(syms, dict) and sym in syms and isinstance(syms[sym], dict):
                            quote_ts = (syms[sym].get("quote_as_of") or syms[sym].get("quote_date")) or None
                        if not quote_ts and _snap.get("quote_as_of"):
                            quote_ts = _snap.get("quote_as_of")
                    as_of_ts = _time.time()
                    lc = compute_position_lifecycle(
                        pos,
                        spot=spot_for_lifecycle,
                        bid=quote.get("bid") if quote else None,
                        ask=quote.get("ask") if quote else None,
                        last=quote.get("last") if quote else None,
                        quote_ts=quote_ts,
                        as_of_ts=as_of_ts,
                        recommended_by=RECOMMENDED_BY_R253,
                    )
                    item["pct_max_profit"] = lc.get("pct_max_profit")
                    item["mark_proxy"] = lc.get("mark_proxy")
                    item["assignment_risk"] = lc.get("assignment_risk")
                    item["roll_window"] = lc.get("roll_window")
                    item["recommended_action_code"] = lc.get("recommended_action_code")
                    item["recommended_by"] = lc.get("recommended_by", "r243")
                    # R24.4: Mark provenance/freshness + roll rationale (never persisted to decision artifact)
                    if lc.get("mark_value") is not None:
                        item["mark_value"] = lc.get("mark_value")
                    if lc.get("mark_source") is not None:
                        item["mark_source"] = lc.get("mark_source")
                    if lc.get("quote_ts") is not None:
                        item["quote_ts"] = lc.get("quote_ts")
                    if lc.get("mark_age_sec") is not None:
                        item["mark_age_sec"] = lc.get("mark_age_sec")
                    if lc.get("roll_window_threshold_dte") is not None:
                        item["roll_window_threshold_dte"] = lc.get("roll_window_threshold_dte")
                    if lc.get("roll_reason_codes") is not None:
                        item["roll_reason_codes"] = lc.get("roll_reason_codes")
                    # R25.3.1: Options lifecycle notifications are emitted during/after eval run only (not here).
            except Exception:
                pass
            # R25.9: Suppress ENTRY from Action Needed when guardrails block (safe labels only)
            next_code = item.get("next_action_code") or "NONE"
            if next_code == "ENTRY" and guardrails_metrics:
                try:
                    ev = evaluate_guardrails_for_entry(
                        guardrails_metrics,
                        {"symbol": sym, "strategy": "OPTIONS"},
                    )
                    if ev.get("status") == "Blocked":
                        continue
                    if ev.get("hard_blocks"):
                        continue
                except Exception:
                    pass
                # R26.0: Portfolio-aware sizing for ENTRY
                try:
                    from app.core.portfolio.sizing_r260 import apply_sizing
                    from app.core.accounts.holdings_db import get_holdings_for_evaluation
                    opt_strategy = (getattr(sel_c, "strategy", None) or "CSP").strip().upper() if sel_c else "CSP"
                    strike_val = getattr(sel_c, "strike", None) or (item.get("strike") if isinstance(item.get("strike"), (int, float)) else None)
                    underlying_price = getattr(summary, "price", None) or getattr(summary, "underlying_price", None)
                    if underlying_price is None and isinstance(diag.get("stock"), dict):
                        underlying_price = diag["stock"].get("price") or diag["stock"].get("underlying_price")
                    try:
                        underlying_price = float(underlying_price) if underlying_price is not None else None
                    except (TypeError, ValueError):
                        underlying_price = None
                    shares_for_sym = (get_holdings_for_evaluation() or {}).get(sym) or 0
                    candidate = {
                        "symbol": sym,
                        "strategy": opt_strategy,
                        "strike": strike_val,
                        "underlying_price": underlying_price,
                        "price": underlying_price,
                        "current_shares_qty": shares_for_sym,
                        "shares": shares_for_sym,
                    }
                    # R26.1: Symbol context for risk proxy (earnings, atr_pct)
                    symbol_context = {}
                    earnings = diag.get("earnings") or {}
                    if isinstance(earnings, dict):
                        symbol_context["earnings_days"] = earnings.get("days")
                        symbol_context["implied_earnings_move_pct"] = earnings.get("implied_move_pct") or earnings.get("implied_earnings_move_pct")
                    technicals = diag.get("technicals") or {}
                    if isinstance(technicals, dict):
                        symbol_context["atr_pct"] = technicals.get("atr_pct")
                    sizing_result = apply_sizing(
                        candidate, guardrails_snapshot, guardrails_metrics,
                        symbol_context=symbol_context,
                    )
                    if sizing_result.get("blocked"):
                        continue
                    item["recommended_contracts"] = sizing_result.get("recommended_contracts")
                    item["recommended_notional_usd"] = sizing_result.get("recommended_notional_usd")
                    item["sizing_constraints_hit"] = sizing_result.get("sizing_constraints_hit") or []
                    item["sizing_recommended_by"] = sizing_result.get("sizing_recommended_by") or "r260"
                    item["recommended_qty"] = None
                    for _k in ("cash_secured_available_usd", "csp_risk_proxy_move_pct", "csp_risk_proxy_loss_per_contract_usd", "csp_risk_proxy_cap_contracts", "csp_risk_proxy_enforced"):
                        if _k in sizing_result:
                            item[_k] = sizing_result[_k]
                except Exception:
                    pass
            options_out.append(item)
        except Exception:
            continue
    _severity_order = {"high": 0, "medium": 1, "low": 2}
    options_out.sort(key=lambda x: (_severity_order.get((x.get("severity") or "low"), 2), (x.get("symbol") or "")))
    options_out = options_out[:5]

    shares_out: List[Dict[str, Any]] = []
    for sym in share_symbols:
        row = store.get_symbol(sym)
        if row is None:
            continue
        summary, candidates, gates, earnings, diagnostics_details = row
        sel_c = next((c for c in (getattr(artifact, "selected_candidates", []) or []) if (getattr(c, "symbol", "") or "").strip().upper() == sym), None)
        _sel_key = getattr(sel_c, "contract_key", None) if sel_c else None
        _opt_sym = getattr(sel_c, "option_symbol", None) if sel_c else None
        _snap = get_eval_snapshot()
        _share_pos = get_share_position(_DEFAULT_ACCOUNT_ID, sym)
        try:
            diag = _build_symbol_diagnostics_from_v2_store(
                summary, candidates, gates, earnings, diagnostics_details, sym,
                selected_contract_key=_sel_key, option_symbol=_opt_sym,
                pipeline_timestamp=(artifact.metadata or {}).get("pipeline_timestamp") if artifact else None,
                run_id=(artifact.metadata or {}).get("run_id") if artifact else None,
                eval_snapshot=_snap,
                shares_position=_share_pos,
            )
            item = _action_needed_item_from_diagnostics(diag, "SHARES")
            # R25.9: Suppress ENTRY when guardrails block
            next_code = item.get("next_action_code") or "NONE"
            if next_code == "ENTRY" and guardrails_metrics:
                try:
                    ev = evaluate_guardrails_for_entry(
                        guardrails_metrics,
                        {"symbol": sym, "strategy": "SHARES"},
                    )
                    if ev.get("status") == "Blocked":
                        continue
                    if ev.get("hard_blocks"):
                        continue
                except Exception:
                    pass
                # R26.0: Portfolio-aware sizing for shares ENTRY
                try:
                    from app.core.portfolio.sizing_r260 import apply_sizing
                    share_price = getattr(summary, "price", None) or getattr(summary, "underlying_price", None)
                    if share_price is None and isinstance(diag.get("stock"), dict):
                        share_price = diag["stock"].get("price") or diag["stock"].get("underlying_price")
                    try:
                        share_price = float(share_price) if share_price is not None else 0.0
                    except (TypeError, ValueError):
                        share_price = 0.0
                    candidate = {"symbol": sym, "strategy": "SHARES", "price": share_price, "underlying_price": share_price}
                    sizing_result = apply_sizing(candidate, guardrails_snapshot, guardrails_metrics)
                    if sizing_result.get("blocked"):
                        continue
                    item["recommended_qty"] = sizing_result.get("recommended_qty")
                    item["recommended_contracts"] = None
                    item["recommended_notional_usd"] = sizing_result.get("recommended_notional_usd")
                    item["sizing_constraints_hit"] = sizing_result.get("sizing_constraints_hit") or []
                    item["sizing_recommended_by"] = sizing_result.get("sizing_recommended_by") or "r260"
                except Exception:
                    pass
            shares_out.append(item)
        except Exception:
            continue
    shares_out.sort(key=lambda x: (_severity_order.get((x.get("severity") or "low"), 2), (x.get("symbol") or "")))
    shares_out = shares_out[:5]

    return {
        "top_options": options_out,
        "top_shares": shares_out,
        "options": options_out,
        "shares": shares_out,
        "recently_changed": _recent_transitions(),
    }


def _enrich_diagnostics_with_options_lifecycle(out: Dict[str, Any], symbol: str) -> None:
    """R25.3: Add options_lifecycle to diagnostics when symbol has an open CSP/CC position (request-time only)."""
    try:
        from app.core.positions.service import list_positions
        from app.core.positions.quote_resolver import find_contract_quote
        from app.core.lifecycle.position_lifecycle_r243 import compute_position_lifecycle, RECOMMENDED_BY_R253
        import time as _time
        open_pos = list_positions(status="OPEN", symbol=symbol, exclude_test=True)
        opt_positions = [p for p in open_pos if (getattr(p, "strategy", "") or "").upper() in ("CSP", "CC")]
        if not opt_positions:
            return
        pos = opt_positions[0]
        chain_rows = out.get("candidates") or []
        expiry = getattr(pos, "expiration", None) or getattr(pos, "expiry", None)
        strike = getattr(pos, "strike", None)
        opt_type = "PUT" if (getattr(pos, "strategy", "") or "").upper() == "CSP" else "CALL"
        quote = find_contract_quote(chain_rows, expiry, strike, opt_type) if chain_rows and expiry and strike is not None else None
        quote_ts = str(quote["quote_ts"]) if quote and quote.get("quote_ts") else None
        stock = out.get("stock") or {}
        spot = float(stock["price"]) if isinstance(stock, dict) and stock.get("price") is not None else None
        as_of_ts = _time.time()
        lc = compute_position_lifecycle(
            pos,
            spot=spot,
            bid=quote.get("bid") if quote else None,
            ask=quote.get("ask") if quote else None,
            last=quote.get("last") if quote else None,
            quote_ts=quote_ts,
            as_of_ts=as_of_ts,
            recommended_by=RECOMMENDED_BY_R253,
        )
        out["options_lifecycle"] = lc
    except Exception:
        pass


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
                pipeline_ts = (artifact.metadata or {}).get("pipeline_timestamp") if artifact else None
                from app.core.eval.evaluation_store_v2 import get_eval_snapshot
                _snap = get_eval_snapshot()
                from app.core.accounts.holdings_db import get_share_position, _DEFAULT_ACCOUNT_ID
                _share_pos = get_share_position(_DEFAULT_ACCOUNT_ID, sym_upper)
                result = _build_symbol_diagnostics_from_v2_store(
                    summary,
                    candidates.get(sym_upper, []),
                    gates.get(sym_upper, []),
                    earnings_by.get(sym_upper),
                    diag_by.get(sym_upper),
                    sym_upper,
                    selected_contract_key=_sel_key,
                    option_symbol=_opt_sym,
                    pipeline_timestamp=pipeline_ts,
                    run_id=(artifact.metadata or {}).get("run_id"),
                    eval_snapshot=_snap,
                    shares_position=_share_pos,
                )
                result["exact_run"] = True
                result["run_id"] = (artifact.metadata or {}).get("run_id")
                _enrich_diagnostics_with_options_lifecycle(result, sym_upper)
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
        pipeline_ts = (artifact.metadata or {}).get("pipeline_timestamp") if artifact else None
        run_id_val = (artifact.metadata or {}).get("run_id") if artifact else None
        from app.core.eval.evaluation_store_v2 import get_eval_snapshot
        _snap = get_eval_snapshot()
        from app.core.accounts.holdings_db import get_share_position, _DEFAULT_ACCOUNT_ID
        _share_pos = get_share_position(_DEFAULT_ACCOUNT_ID, sym_upper)
        out = _build_symbol_diagnostics_from_v2_store(
            summary, candidates, gates, earnings, diagnostics_details, sym_upper,
            selected_contract_key=_sel_key, option_symbol=_opt_sym, pipeline_timestamp=pipeline_ts,
            run_id=run_id_val,
            eval_snapshot=_snap,
            shares_position=_share_pos,
        )
        if run_id and run_id.strip():
            out["exact_run"] = False
            out["run_id"] = None
        _enrich_diagnostics_with_options_lifecycle(out, sym_upper)
        return out

    # Symbol not in store — 404 (no legacy path; use recompute=1 to add symbol)
    raise HTTPException(status_code=404, detail=f"Symbol {sym_upper} not in evaluation store. Use recompute=1 to evaluate.")


def get_symbol_diagnostics_for_copilot(symbol: str) -> Optional[Dict[str, Any]]:
    """
    R23.4: Return symbol diagnostics from store for copilot tools (read-only, no auth).
    Returns None if symbol not in store. Caller must not persist result into decision artifacts.
    """
    sym_upper = (symbol or "").strip().upper()
    if not sym_upper:
        return None
    from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2, get_eval_snapshot
    from app.core.accounts.holdings_db import get_share_position, _DEFAULT_ACCOUNT_ID
    store = get_evaluation_store_v2()
    store.reload_from_disk()
    row = store.get_symbol(sym_upper)
    if row is None:
        return None
    summary, candidates, gates, earnings, diagnostics_details = row
    artifact = store.get_latest()
    sel_c = next(
        (c for c in (getattr(artifact, "selected_candidates", []) or [])
        if (getattr(c, "symbol", "") or "").strip().upper() == sym_upper
    ), None) if artifact else None
    _sel_key = getattr(sel_c, "contract_key", None) if sel_c else None
    _opt_sym = getattr(sel_c, "option_symbol", None) if sel_c else None
    pipeline_ts = (artifact.metadata or {}).get("pipeline_timestamp") if artifact else None
    run_id_val = (artifact.metadata or {}).get("run_id") if artifact else None
    _snap = get_eval_snapshot()
    _share_pos = get_share_position(_DEFAULT_ACCOUNT_ID, sym_upper)
    return _build_symbol_diagnostics_from_v2_store(
        summary, candidates, gates, earnings, diagnostics_details, sym_upper,
        selected_contract_key=_sel_key, option_symbol=_opt_sym, pipeline_timestamp=pipeline_ts,
        run_id=run_id_val,
        eval_snapshot=_snap,
        shares_position=_share_pos,
    )


@router.get("/shares-candidates")
def ui_shares_candidates(
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """R22.5: Shares candidates (BUY SHARES recommendation only). No broker/order placement."""
    _require_ui_key(x_ui_key)
    from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
    store = get_evaluation_store_v2()
    store.reload_from_disk()
    artifact = store.get_latest()
    if artifact is None:
        return {"shares_candidates": []}
    symbols = getattr(artifact, "symbols", []) or []
    diag_by = getattr(artifact, "diagnostics_by_symbol", {}) or {}
    out: List[Dict[str, Any]] = []
    for s in symbols:
        sym = (getattr(s, "symbol", "") or "").strip().upper()
        if not sym:
            continue
        diag = diag_by.get(sym)
        if diag is not None and hasattr(diag, "to_dict"):
            diag = diag.to_dict() if callable(getattr(diag, "to_dict", None)) else diag
        diag = diag or {}
        technicals = diag.get("technicals") or {}
        exit_plan = diag.get("exit_plan") or {}
        hold_time = _build_hold_time_estimate_at_request_time(technicals, exit_plan)
        plan = _build_shares_plan_at_request_time(s, technicals, exit_plan, hold_time, sym)
        if plan is not None:
            out.append(plan)
    return {"shares_candidates": out}


@router.post("/symbols/{symbol}/recompute")
def ui_symbol_recompute(
    symbol: str = Path(..., min_length=1, max_length=12),
    force: bool = Query(False, description="Override market-closed guardrail; if true bypass snapshot (use fresh data)"),
    x_ui_key: str | None = Header(None, alias="x-ui-key"),
) -> Dict[str, Any]:
    """
    Run full evaluation for one symbol and merge into the canonical store.
    R22.7 Fix Pack: When force=false and eval snapshot is fresh (< N min), uses snapshot (no re-run) for determinism.
    When force=true, always re-runs with fresh data.
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
    from app.core.eval.evaluation_store_v2 import (
        get_evaluation_store_v2,
        get_eval_snapshot,
        eval_snapshot_is_fresh,
    )
    store = get_evaluation_store_v2()
    store.reload_from_disk()
    merged = None
    snapshot_used = False
    if not force:
        snapshot = get_eval_snapshot()
        if snapshot and eval_snapshot_is_fresh(snapshot):
            row = store.get_symbol(sym_upper)
            if row is not None:
                snapshot_used = True
                summary, _c, _g, _e, _d = row
                artifact = store.get_latest()
                meta = (artifact.metadata or {}) if artifact else {}
                ts = meta.get("pipeline_timestamp") or (snapshot.get("pipeline_timestamp") or "")
                result: Dict[str, Any] = {
                    "symbol": sym_upper,
                    "pipeline_timestamp": ts,
                    "artifact_version": "v2",
                    "updated": False,
                    "snapshot_used": True,
                    "score": summary.score,
                    "band": summary.band,
                    "verdict": summary.verdict,
                }
                return result
    if not snapshot_used:
        try:
            from app.core.eval.evaluation_service_v2 import evaluate_single_symbol_and_merge
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
    store.reload_from_disk()
    row = store.get_symbol(sym_upper)
    meta = (merged.metadata or {}) if merged else (store.get_latest().metadata or {} if store.get_latest() else {})
    ts = meta.get("pipeline_timestamp") or ""
    result = {
        "symbol": sym_upper,
        "pipeline_timestamp": ts,
        "artifact_version": "v2",
        "updated": not snapshot_used,
        "snapshot_used": snapshot_used,
    }
    if row is not None:
        summary, _candidates, _gates, _earnings, _diag = row
        result["score"] = summary.score
        result["band"] = summary.band
        result["verdict"] = summary.verdict
    return result
