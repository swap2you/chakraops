# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40.1: Exclusive universe-evaluation coordinator (single lock, v2 engine)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_COORD_META_LOCK = threading.Lock()
_ACTIVE_TRIGGER: Optional[str] = None
_ACTIVE_RUN_ID: Optional[str] = None


def try_begin_universe_evaluation(trigger: str) -> Tuple[bool, str]:
    """
    Acquire the shared run lock for a full-universe evaluation.
    Returns (True, run_id) on success, or (False, \"already_running\").
    """
    from app.core.eval.evaluation_store import acquire_run_lock, generate_run_id

    global _ACTIVE_TRIGGER, _ACTIVE_RUN_ID
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
    logger.info("[EVAL_COORD] begin trigger=%s run_id=%s", _ACTIVE_TRIGGER, run_id)
    return True, run_id


def end_universe_evaluation(run_id: Optional[str] = None) -> None:
    """Release the shared run lock for the owning run_id when known."""
    from app.core.eval.evaluation_store import release_run_lock

    global _ACTIVE_TRIGGER, _ACTIVE_RUN_ID
    with _COORD_META_LOCK:
        trigger = _ACTIVE_TRIGGER
        active_run_id = _ACTIVE_RUN_ID
        expected = run_id or active_run_id
        _ACTIVE_TRIGGER = None
        _ACTIVE_RUN_ID = None
    try:
        release_run_lock(expected_run_id=expected)
    finally:
        logger.info("[EVAL_COORD] end trigger=%s run_id=%s", trigger, expected)


def run_universe_evaluation_exclusive(
    symbols: List[str],
    *,
    mode: str = "LIVE",
    trigger: str = "api",
) -> Dict[str, Any]:
    """
    Run evaluate_universe (v2) under the exclusive run lock.

    On lock contention returns ``{started: False, reason: \"already_running\"}``.
    On success returns ``{started: True, reason: \"ok\", run_id, artifact, ...}``.
    """
    ok, token = try_begin_universe_evaluation(trigger)
    if not ok:
        return {"started": False, "reason": token, "run_id": None}

    run_id = token
    try:
        from app.core.eval.evaluation_service_v2 import evaluate_universe
        from app.core.eval.evaluation_store import update_latest_pointer

        artifact = evaluate_universe(list(symbols), mode=mode)
        meta = getattr(artifact, "metadata", None) or {}
        # Align artifact run identity with coordinator lock when possible.
        try:
            if hasattr(artifact, "metadata") and isinstance(artifact.metadata, dict):
                artifact.metadata["coordinator_run_id"] = run_id
                artifact.metadata["trigger"] = trigger
        except Exception:
            pass
        completed_at = datetime.now(timezone.utc).isoformat()
        try:
            update_latest_pointer(run_id, completed_at)
        except Exception:
            logger.exception("[EVAL_COORD] update_latest_pointer failed run_id=%s", run_id)
        return {
            "started": True,
            "reason": "ok",
            "run_id": run_id,
            "trigger": trigger,
            "artifact": artifact,
            "pipeline_timestamp": meta.get("pipeline_timestamp"),
            "counts": {
                "universe_size": meta.get("universe_size", 0),
                "evaluated_count_stage1": meta.get("evaluated_count_stage1", 0),
                "evaluated_count_stage2": meta.get("evaluated_count_stage2", 0),
                "eligible_count": meta.get("eligible_count", 0),
            },
        }
    except Exception:
        logger.exception("[EVAL_COORD] evaluate_universe failed trigger=%s run_id=%s", trigger, run_id)
        raise
    finally:
        end_universe_evaluation(run_id=run_id)
