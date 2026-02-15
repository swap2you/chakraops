# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase UI-1: Evaluation run and symbol drilldown API routes."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_latest_run() -> Optional[Dict[str, Any]]:
    """Load latest completed run from artifacts or evaluation store."""
    try:
        from app.core.eval.run_artifacts import build_latest_response_from_artifacts
        from app.core.eval.evaluation_store import build_latest_response
        resp = build_latest_response_from_artifacts() or build_latest_response()
        if not resp.get("has_completed_run"):
            return None
        return resp
    except Exception as e:
        logger.warning("[EVAL_API] get_latest_run failed: %s", e)
        return None


def build_latest_run_response() -> Dict[str, Any]:
    """
    GET /api/eval/latest-run response.
    """
    run = _get_latest_run()
    if not run:
        return {
            "run_id": None,
            "as_of": None,
            "status": "NO_RUNS",
            "duration_sec": 0,
            "symbols_evaluated": 0,
            "symbols_skipped": 0,
            "top_ranked": [],
            "warnings": [],
            "throughput": {"wall_time_sec": 0, "requests_estimated": None, "cache_hit_rate_by_endpoint": {}},
        }

    try:
        from app.core.eval.run_diagnostics_store import load_run_diagnostics
        diag = load_run_diagnostics()
    except Exception:
        diag = None

    # Map symbols to top_ranked (top candidates + holds, key metrics)
    symbols = run.get("symbols") or []
    top_candidates = run.get("top_candidates") or []
    top_holds = run.get("top_holds") or []
    by_symbol = {s.get("symbol"): s for s in symbols if s.get("symbol")}
    top_ranked: List[Dict[str, Any]] = []
    seen: set = set()
    for c in top_candidates + top_holds:
        sym = c.get("symbol")
        if not sym or sym in seen:
            continue
        seen.add(sym)
        full = by_symbol.get(sym, c)
        sc = full.get("selected_contract") or {}
        contract = sc.get("contract", sc) if isinstance(sc, dict) else sc
        ch = full.get("capital_hint") or {}
        top_ranked.append({
            "symbol": sym,
            "status": full.get("verdict", c.get("verdict")),
            "score": full.get("score", c.get("score")),
            "band": ch.get("band") if isinstance(ch, dict) else getattr(ch, "band", None),
            "mode": "CSP",  # primary strategy
            "strike": contract.get("strike") if isinstance(contract, dict) else getattr(contract, "strike", None),
            "dte": contract.get("dte") if isinstance(contract, dict) else getattr(contract, "dte", None),
            "premium": contract.get("bid") if isinstance(contract, dict) else getattr(contract, "bid", None),
            "primary_reason": full.get("primary_reason"),
        })

    # Warnings from diagnostics
    warnings: List[str] = []
    if diag:
        for w in diag.get("watchdog_warnings") or []:
            reason = w.get("reason") or w.get("failed")
            if reason:
                warnings.append(str(reason))
        if diag.get("budget_warning"):
            warnings.append(diag["budget_warning"])

    throughput: Dict[str, Any] = {
        "wall_time_sec": run.get("duration_seconds", 0),
        "requests_estimated": None,
        "cache_hit_rate_by_endpoint": {},
    }
    if diag:
        throughput["wall_time_sec"] = diag.get("wall_time_sec", throughput["wall_time_sec"])
        throughput["requests_estimated"] = diag.get("requests_estimated")
        throughput["cache_hit_rate_by_endpoint"] = diag.get("cache_hit_rate_by_endpoint") or {}

    # symbols_skipped from gate skips
    symbols_skipped = 0
    if diag:
        symbols_skipped = diag.get("gate_skips_count", 0)

    return {
        "run_id": run.get("run_id"),
        "as_of": run.get("completed_at"),
        "status": run.get("status", "COMPLETED"),
        "duration_sec": run.get("duration_seconds", 0),
        "symbols_evaluated": run.get("counts", {}).get("evaluated", len(symbols)),
        "symbols_skipped": symbols_skipped,
        "top_ranked": top_ranked,
        "warnings": warnings,
        "throughput": throughput,
    }


def build_symbol_response(symbol: str) -> Dict[str, Any]:
    """
    GET /api/eval/symbol/{symbol} response.
    """
    run = _get_latest_run()
    if not run:
        return {"symbol": symbol, "error": "No completed run"}

    symbols = run.get("symbols") or []
    sym_upper = (symbol or "").strip().upper()
    found = next((s for s in symbols if (s.get("symbol") or "").strip().upper() == sym_upper), None)
    if not found:
        return {"symbol": sym_upper, "error": "Symbol not in latest run"}

    # Stage 1
    symbol_eligibility = found.get("symbol_eligibility") or {}
    data_sufficiency = {
        "required_data_missing": symbol_eligibility.get("required_data_missing") or [],
        "required_data_stale": symbol_eligibility.get("required_data_stale") or [],
        "status": symbol_eligibility.get("status"),
    }
    stage1 = {
        "data_sufficiency": data_sufficiency,
        "data_as_of": found.get("quote_date") or found.get("fetched_at"),
        "endpoints_used": found.get("field_sources") or found.get("data_sources") or [],
    }

    # Stage 2
    contract_data = found.get("contract_data") or {}
    contract_eligibility = found.get("contract_eligibility") or {}
    sc = found.get("selected_contract") or {}
    ch = found.get("capital_hint") or {}
    stage2 = {
        "candidate_contract": sc.get("contract", sc) if isinstance(sc, dict) else sc,
        "score": found.get("score"),
        "band": ch.get("band") if isinstance(ch, dict) else getattr(ch, "band", None),
        "eligibility": {
            "status": contract_eligibility.get("status"),
            "primary_reason": contract_eligibility.get("primary_reason") or found.get("primary_reason"),
        },
        "fail_reasons": contract_eligibility.get("fail_reasons") or [],
    }

    # Sizing / guardrails
    sizing: Dict[str, Any] = {
        "baseline_contracts": None,
        "guardrail_adjusted_contracts": None,
        "advisories": [],
    }
    if ch and isinstance(ch, dict):
        sizing["advisories"].append(ch.get("band_reason") or "")
    sizing["advisories"] = [a for a in sizing["advisories"] if a]

    # Exit plan (from trade proposal if available; else placeholders)
    exit_plan: Dict[str, Any] = {
        "t1": None,
        "t2": None,
        "dte_targets": None,
        "priority": None,
    }

    # Traces
    traces = {
        "eligibility_trace": {
            "symbol_eligibility": symbol_eligibility,
            "contract_data": contract_data,
            "contract_eligibility": contract_eligibility,
        },
        "computed_fields": {
            "data_completeness": found.get("data_completeness"),
            "score_breakdown": found.get("score_breakdown"),
            "rank_reasons": found.get("rank_reasons"),
        },
    }

    return {
        "symbol": sym_upper,
        "stage1": stage1,
        "stage2": stage2,
        "sizing": sizing,
        "exit_plan": exit_plan,
        "traces": traces,
    }


def build_system_health_response() -> Dict[str, Any]:
    """
    GET /api/system/health response.
    """
    try:
        from app.core.eval.run_diagnostics_store import load_run_diagnostics
        diag = load_run_diagnostics()
    except Exception:
        diag = None

    # Last 10 run IDs (optional)
    recent_run_ids: List[str] = []
    try:
        from app.core.eval.evaluation_store import list_runs
        for s in list_runs(limit=10):
            rid = getattr(s, "run_id", None) or (s.get("run_id") if isinstance(s, dict) else None)
            if rid:
                recent_run_ids.append(rid)
    except Exception:
        pass

    if not diag:
        return {
            "run_id": None,
            "as_of": None,
            "watchdog": {"warnings": []},
            "cache": {},
            "budget": {},
            "recent_run_ids": recent_run_ids,
        }

    return {
        "run_id": diag.get("run_id"),
        "as_of": diag.get("as_of"),
        "watchdog": {
            "warnings": diag.get("watchdog_warnings") or [],
        },
        "cache": {
            "cache_hit_rate_pct": diag.get("cache_hit_rate_pct"),
            "cache_hit_rate_by_endpoint": diag.get("cache_hit_rate_by_endpoint") or {},
        },
        "budget": {
            "requests_estimated": diag.get("requests_estimated"),
            "max_requests_estimate": diag.get("max_requests_estimate"),
            "budget_stopped": diag.get("budget_stopped"),
            "budget_warning": diag.get("budget_warning"),
        },
        "recent_run_ids": recent_run_ids,
    }
