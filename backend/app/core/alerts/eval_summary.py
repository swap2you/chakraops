# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R21.5.2: Evaluation heartbeat/summary for Slack daily channel. No ORATS; throttle for scheduler."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Scheduler tick registration: when scheduler starts a run, server calls set_scheduler_tick_for_run(run_id, tick).
# process_run_completed uses it to apply EVAL_SUMMARY_EVERY_N_TICKS throttle (scheduler only).
_scheduler_tick_by_run_id: Dict[str, int] = {}


def set_scheduler_tick_for_run(run_id: str, tick: int) -> None:
    """Register that this run was started by the scheduler as tick N. Call from scheduler when started=True."""
    _scheduler_tick_by_run_id[run_id] = tick


def get_scheduler_tick_for_run(run_id: str) -> Optional[int]:
    """Return tick index if this run was started by scheduler, else None (e.g. Force run)."""
    return _scheduler_tick_by_run_id.get(run_id)


def _assign_band(score: Optional[float]) -> str:
    """A|B|C|D from score. Match decision_artifact_v2.assign_band."""
    if score is None:
        return "D"
    try:
        from app.core.eval.decision_artifact_v2 import assign_band
        return assign_band(score)
    except Exception:
        s = float(score)
        if s >= 80:
            return "A"
        if s >= 60:
            return "B"
        if s >= 40:
            return "C"
        return "D"


def build_eval_summary_payload(
    run: Any,
    sent_by_channel: Optional[Dict[str, int]] = None,
    duration_ms: Optional[float] = None,
    last_run_ok: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Build EVAL_SUMMARY payload from run only (no ORATS). Used for Slack daily heartbeat.
    sent_by_channel: optional {signals: n, data_health: n, critical: n} from this run's sends.
    """
    symbols = getattr(run, "symbols", None) or []
    total = getattr(run, "total", None) or getattr(run, "evaluated", None) or len(symbols)
    eligible = getattr(run, "eligible", None)
    if eligible is None:
        eligible = sum(1 for s in symbols if isinstance(s, dict) and s.get("verdict") == "ELIGIBLE")
    blocks = sum(1 for s in symbols if isinstance(s, dict) and s.get("verdict") == "BLOCKED")
    a_count = 0
    b_count = 0
    for s in symbols:
        if not isinstance(s, dict):
            continue
        band = _assign_band(s.get("score"))
        if band == "A":
            a_count += 1
        elif band == "B":
            b_count += 1

    run_id = getattr(run, "run_id", None) or "?"
    completed_at = getattr(run, "completed_at", None) or ""
    mode = os.getenv("EVAL_MODE", "LIVE").strip().upper()
    if mode not in ("LIVE", "MOCK"):
        mode = "LIVE"

    top_eligibles: list = []
    try:
        top_candidates = getattr(run, "top_candidates", None) or []
        for c in (top_candidates[:3] if isinstance(top_candidates, list) else []):
            if not isinstance(c, dict):
                continue
            sym = c.get("symbol", "?")
            ct = c.get("candidate_trades") or []
            strategy = ct[0].get("strategy", "CSP") if isinstance(ct, list) and ct else c.get("strategy", "CSP") or "CSP"
            score = c.get("score")
            band = _assign_band(score)
            top_eligibles.append({"symbol": sym, "strategy": strategy, "score": score, "band": band})
    except Exception:
        pass

    payload: Dict[str, Any] = {
        "payload_type": "EVAL_SUMMARY",
        "mode": mode,
        "run_id": run_id,
        "timestamp": completed_at,
        "total": total,
        "eligible": eligible,
        "a_tier": a_count,
        "b_tier": b_count,
        "blocked": blocks,
        "top_eligibles": top_eligibles,
        "duration_ms": duration_ms,
        "last_run_ok": last_run_ok if last_run_ok is not None else (getattr(run, "status", None) == "COMPLETED"),
    }
    if sent_by_channel:
        payload["alerts_sent"] = sent_by_channel

    # Canonical read-only broker freshness (never journal/unified counts).
    try:
        from app.core.portfolio.capital_authority_r70 import get_broker_freshness_view

        bv = get_broker_freshness_view("acct_individual")
        payload["broker_state"] = bv.get("state") or "UNAVAILABLE"
        payload["account_alias"] = bv.get("account_alias") or "acct_individual"
        payload["broker_as_of"] = bv.get("as_of")
        payload["broker_age_minutes"] = bv.get("age_minutes")
        payload["broker_source"] = bv.get("source")
        payload["open_positions"] = bv.get("broker_open_display") or "UNKNOWN"
        payload["broker_open_display"] = payload["open_positions"]
        payload["sizing_blocked"] = bool(bv.get("sizing_blocked", True))
    except Exception as e:
        logger.debug("[ALERTS] broker freshness for eval summary unavailable: %s", e)
        payload["broker_state"] = "UNAVAILABLE"
        payload["open_positions"] = "UNKNOWN"
        payload["broker_open_display"] = "UNKNOWN"
        payload["sizing_blocked"] = True
        payload["account_alias"] = "acct_individual"

    # ORATS / data-health honesty for actionability.
    try:
        from app.api.data_health import get_orats_freshness_state

        of = get_orats_freshness_state() or {}
        orats_state = str(of.get("state") or of.get("state_label") or "UNKNOWN").upper()
        payload["orats_state"] = orats_state
        payload["orats_as_of"] = of.get("as_of")
        if orats_state in ("ERROR", "WARN", "DELAYED") or payload.get("broker_state") != "FRESH":
            payload["actionability"] = "DATA NOT ACTIONABLE"
            payload["data_health_state"] = "DATA NOT ACTIONABLE"
        else:
            payload["actionability"] = "OK"
            payload["data_health_state"] = "OK"
    except Exception as e:
        logger.debug("[ALERTS] ORATS freshness for eval summary unavailable: %s", e)
        payload["orats_state"] = "UNKNOWN"
        payload["actionability"] = "DATA NOT ACTIONABLE"
        payload["data_health_state"] = "DATA NOT ACTIONABLE"

    return payload


def should_send_eval_summary_this_run(run_id: str) -> bool:
    """
    True if we should send EVAL_SUMMARY for this run.
    Force run (tick is None): always True. Scheduler run: True only when (tick % EVAL_SUMMARY_EVERY_N_TICKS) == 0.
    SKIPPED scheduler ticks never reach this (process_run_completed only runs on completed runs).
    """
    tick = get_scheduler_tick_for_run(run_id)
    if tick is None:
        return True  # Force or unknown -> send
    try:
        n = int(os.getenv("EVAL_SUMMARY_EVERY_N_TICKS", "1").strip())
    except (ValueError, TypeError):
        n = 1
    if n < 1:
        n = 1
    if (tick % n) != 0:
        logger.info(
            "[ALERTS] EVAL_SUMMARY suppressed (throttle): run_id=%s scheduler_tick=%s every_n=%s (send every Nth scheduler run)",
            run_id, tick, n,
        )
        return False
    return True
