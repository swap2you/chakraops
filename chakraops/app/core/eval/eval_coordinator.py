# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40.1: Exclusive universe-evaluation coordinator (single lock, v2 engine).

R70-DEF-040: This module is the PRIMARY LIVE full-universe evaluation authority.
Secondary / diagnostic writers (scripts/run_and_save.py, single-symbol merge,
legacy evaluate-now before cutover) must be labeled and must not compete for
LIVE decision authority.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# R70-DEF-040: inventory tests assert this marker on the exclusive coordinator.
PRIMARY_LIVE_EVAL_AUTHORITY = True

_COORD_META_LOCK = threading.Lock()
_ACTIVE_TRIGGER: Optional[str] = None
_ACTIVE_RUN_ID: Optional[str] = None
_ACTIVE_STARTED_AT: Optional[str] = None


def try_begin_universe_evaluation(trigger: str) -> Tuple[bool, str]:
    """
    Acquire the shared run lock for a full-universe evaluation.
    Returns (True, run_id) on success, or (False, \"already_running\").
    """
    from app.core.eval.evaluation_store import (
        acquire_run_lock,
        generate_run_id,
        map_eval_trigger_to_source,
        write_run_running,
    )

    global _ACTIVE_TRIGGER, _ACTIVE_RUN_ID, _ACTIVE_STARTED_AT
    run_id = generate_run_id()
    started_at = datetime.now(timezone.utc).isoformat()
    if not acquire_run_lock(run_id, started_at):
        logger.info(
            "[EVAL_COORD] lock busy trigger=%s active_trigger=%s active_run_id=%s",
            trigger,
            _ACTIVE_TRIGGER,
            _ACTIVE_RUN_ID,
        )
        return False, "already_running"
    with _COORD_META_LOCK:
        _ACTIVE_TRIGGER = trigger or "unknown"
        _ACTIVE_RUN_ID = run_id
        _ACTIVE_STARTED_AT = started_at
    try:
        write_run_running(run_id, started_at, source=map_eval_trigger_to_source(trigger))
    except Exception:
        logger.exception("[EVAL_COORD] write_run_running failed run_id=%s", run_id)
    logger.info("[EVAL_COORD] begin trigger=%s run_id=%s", _ACTIVE_TRIGGER, run_id)
    return True, run_id


def end_universe_evaluation(run_id: Optional[str] = None) -> None:
    """Release the shared run lock for the owning run_id when known."""
    from app.core.eval.evaluation_store import release_run_lock

    global _ACTIVE_TRIGGER, _ACTIVE_RUN_ID, _ACTIVE_STARTED_AT
    with _COORD_META_LOCK:
        trigger = _ACTIVE_TRIGGER
        active_run_id = _ACTIVE_RUN_ID
        expected = run_id or active_run_id
        _ACTIVE_TRIGGER = None
        _ACTIVE_RUN_ID = None
        _ACTIVE_STARTED_AT = None
    try:
        release_run_lock(expected_run_id=expected)
    finally:
        logger.info("[EVAL_COORD] end trigger=%s run_id=%s", trigger, expected)


def run_universe_evaluation_exclusive(
    symbols: List[str],
    *,
    mode: str = "LIVE",
    trigger: str = "api",
    allow_when_closed: bool = False,
) -> Dict[str, Any]:
    """
    Run evaluate_universe (v2) under the exclusive run lock.

    On lock contention returns ``{started: False, reason: \"already_running\"}``.
    On market closed (normal LIVE) returns ``{started: False, reason: \"market_closed\", market_phase}``
    without creating a RUNNING stub unless ``allow_when_closed=True``.
    On success returns ``{started: True, reason: \"ok\", run_id, artifact, ...}``.
    Persists v1 ledger run + latest pointer so last_completed_run_id advances (R70-DEF-032).
    """
    # R70-ABCD Batch B: server-owned market gate for LIVE authority path.
    if not allow_when_closed:
        try:
            from app.market.market_hours import get_market_phase

            phase = (get_market_phase() or "UNKNOWN").strip().upper()
        except Exception:
            phase = "UNKNOWN"
        if phase != "OPEN":
            logger.info(
                "[EVAL_COORD] refuse market_closed trigger=%s phase=%s",
                trigger,
                phase,
            )
            return {
                "started": False,
                "reason": "market_closed",
                "code": "MARKET_CLOSED",
                "market_phase": phase,
                "run_id": None,
                "manual_only": True,
                "trade_execution": False,
            }

    ok, token = try_begin_universe_evaluation(trigger)
    if not ok:
        return {"started": False, "reason": token, "run_id": None}

    run_id = token
    with _COORD_META_LOCK:
        started_at = _ACTIVE_STARTED_AT or datetime.now(timezone.utc).isoformat()
        active_trigger = _ACTIVE_TRIGGER or trigger
    try:
        from app.core.eval.evaluation_service_v2 import evaluate_universe
        from app.core.eval.evaluation_store import (
            EvaluationRunFull,
            map_eval_trigger_to_source,
            save_run,
            update_latest_pointer,
        )

        artifact = evaluate_universe(list(symbols), mode=mode)
        meta = getattr(artifact, "metadata", None) or {}
        # Align artifact run identity with coordinator lock when possible.
        try:
            if hasattr(artifact, "metadata") and isinstance(artifact.metadata, dict):
                artifact.metadata["coordinator_run_id"] = run_id
                artifact.metadata["trigger"] = active_trigger
        except Exception:
            pass
        completed_at = datetime.now(timezone.utc).isoformat()
        try:
            started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            completed_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            duration = max(0.0, (completed_dt - started_dt).total_seconds())
        except Exception:
            duration = float(meta.get("duration_seconds") or 0.0)
        ledger = EvaluationRunFull(
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            status="COMPLETED",
            duration_seconds=duration,
            total=int(meta.get("universe_size") or len(symbols) or 0),
            evaluated=int(meta.get("evaluated_count_stage1") or 0),
            eligible=int(meta.get("eligible_count") or 0),
            shortlisted=int(meta.get("shortlisted_count") or meta.get("eligible_count") or 0),
            stage1_pass=int(meta.get("evaluated_count_stage1") or 0),
            stage2_pass=int(meta.get("evaluated_count_stage2") or 0),
            source=map_eval_trigger_to_source(active_trigger),
            engine="staged",
            correlation_id=run_id,
            market_phase=str(meta.get("market_phase") or "") or None,
        )
        try:
            save_run(ledger)
            update_latest_pointer(run_id, completed_at)
        except Exception:
            logger.exception("[EVAL_COORD] ledger persist failed run_id=%s", run_id)
            raise
        return {
            "started": True,
            "reason": "ok",
            "run_id": run_id,
            "trigger": active_trigger,
            "artifact": artifact,
            "pipeline_timestamp": meta.get("pipeline_timestamp"),
            "counts": {
                "universe_size": meta.get("universe_size", 0),
                "evaluated_count_stage1": meta.get("evaluated_count_stage1", 0),
                "evaluated_count_stage2": meta.get("evaluated_count_stage2", 0),
                "eligible_count": meta.get("eligible_count", 0),
            },
            "ledger_persisted": True,
        }
    except Exception as exc:
        logger.exception("[EVAL_COORD] evaluate_universe failed trigger=%s run_id=%s", trigger, run_id)
        try:
            from app.core.eval.evaluation_store import map_eval_trigger_to_source, save_failed_run

            save_failed_run(
                run_id,
                reason=f"evaluate_failed:{type(exc).__name__}",
                error=exc,
                started_at=started_at,
                source=map_eval_trigger_to_source(active_trigger),
            )
        except Exception:
            logger.exception("[EVAL_COORD] save_failed_run failed run_id=%s", run_id)
        raise
    finally:
        end_universe_evaluation(run_id=run_id)
