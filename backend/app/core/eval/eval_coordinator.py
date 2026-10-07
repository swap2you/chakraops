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


def _ledger_symbols_and_candidates_from_artifact(artifact: Any) -> tuple[list, list]:
    """Normalize DecisionArtifactV2 into ledger symbols + top_candidates (artifact only)."""
    from app.core.eval.decision_artifact_v2 import assign_band

    symbols_out: list = []
    candidates_by_sym: dict = {}
    try:
        cbs = getattr(artifact, "candidates_by_symbol", None) or {}
        if isinstance(cbs, dict):
            for k, rows in cbs.items():
                candidates_by_sym[str(k).strip().upper()] = list(rows or [])
    except Exception:
        candidates_by_sym = {}

    for s in getattr(artifact, "symbols", None) or []:
        try:
            sym = (getattr(s, "symbol", None) or "").strip().upper()
            if not sym:
                continue
            verd = str(getattr(s, "verdict", "") or getattr(s, "final_verdict", "") or "").strip().upper()
            score = getattr(s, "score", None)
            if score is None:
                score = getattr(s, "final_score", None)
            band = getattr(s, "band", None) or assign_band(score)
            strategy = getattr(s, "strategy", None) or "CSP"
            primary_reason = getattr(s, "primary_reason", None)
            if not primary_reason:
                codes = getattr(s, "primary_reason_codes", None) or []
                if codes:
                    primary_reason = ",".join(str(c) for c in codes[:3])
            cand_rows = candidates_by_sym.get(sym) or []
            # Prefer selected_candidates matching this symbol from artifact-level list.
            if not cand_rows:
                for sc in getattr(artifact, "selected_candidates", None) or []:
                    if (getattr(sc, "symbol", "") or "").strip().upper() == sym:
                        cand_rows.append(sc)
            candidate_trades = []
            for ct in cand_rows:
                if hasattr(ct, "to_dict"):
                    d = ct.to_dict()
                elif isinstance(ct, dict):
                    d = dict(ct)
                else:
                    d = {
                        "strategy": getattr(ct, "strategy", strategy),
                        "expiry": getattr(ct, "expiry", None),
                        "strike": getattr(ct, "strike", None),
                        "delta": getattr(ct, "delta", None),
                        "credit_estimate": getattr(ct, "credit_estimate", None),
                        "max_loss": getattr(ct, "max_loss", None),
                        "contract_key": getattr(ct, "contract_key", None),
                        "option_symbol": getattr(ct, "option_symbol", None),
                        "why_this_trade": getattr(ct, "why_this_trade", None),
                    }
                # Normalize keys used by Slack signal builder.
                d.setdefault("strategy", strategy)
                if d.get("expiry") and not d.get("expiration"):
                    d["expiration"] = d.get("expiry")
                candidate_trades.append(d)
            row = {
                "symbol": sym,
                "verdict": verd or "NOT_EVALUATED",
                "score": score,
                "band": band,
                "strategy": strategy,
                "primary_reason": primary_reason,
                "expiration": getattr(s, "expiration", None),
                "price": getattr(s, "price", None) or getattr(s, "underlying_price", None),
                "candidate_trades": candidate_trades,
                "has_candidates": bool(candidate_trades) or bool(getattr(s, "has_candidates", False)),
                "candidate_count": len(candidate_trades) or int(getattr(s, "candidate_count", 0) or 0),
            }
            # Prefer first candidate contract identity onto the symbol row for convenience.
            if candidate_trades:
                first = candidate_trades[0]
                row["selected_expiration"] = first.get("expiration") or first.get("expiry")
                row["selected_strike"] = first.get("strike")
                row["selected_contract_key"] = first.get("contract_key") or first.get("option_symbol")
                if first.get("strategy"):
                    row["strategy"] = first.get("strategy")
            symbols_out.append(row)
        except Exception:
            logger.debug("[EVAL_COORD] skip symbol row for ledger", exc_info=True)
            continue

    eligible = [r for r in symbols_out if r.get("verdict") == "ELIGIBLE"]
    top_candidates = sorted(
        eligible,
        key=lambda x: float(x.get("score") or 0),
        reverse=True,
    )[:10]
    return symbols_out, top_candidates


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
        from app.core.eval.evaluation_service_v2 import (
            _coordinator_live_universe_write_scope,
            evaluate_universe,
        )
        from app.core.eval.evaluation_store import (
            EvaluationRunFull,
            map_eval_trigger_to_source,
            save_run,
            update_latest_pointer,
        )

        with _coordinator_live_universe_write_scope():
            artifact = evaluate_universe(
                list(symbols), mode=mode, coordinator_run_id=run_id
            )
        meta = getattr(artifact, "metadata", None) or {}
        # Defense-in-depth: ensure in-memory artifact still carries coordinator id.
        try:
            if hasattr(artifact, "metadata") and isinstance(artifact.metadata, dict):
                artifact.metadata["coordinator_run_id"] = run_id
                artifact.metadata["run_id"] = run_id
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

        # Tally HOLD / BLOCKED from artifact symbols (ledger counters)
        hold_n = 0
        block_n = 0
        top_holds: List[Dict[str, Any]] = []
        try:
            for s in getattr(artifact, "symbols", None) or []:
                verd = str(getattr(s, "verdict", "") or "").strip().upper()
                if verd in ("HOLD", "HELD"):
                    hold_n += 1
                    if len(top_holds) < 10:
                        top_holds.append(
                            {
                                "symbol": getattr(s, "symbol", None),
                                "verdict": verd,
                                "reason": getattr(s, "primary_reason", None),
                                "score": getattr(s, "score", None),
                            }
                        )
                elif verd in ("BLOCKED", "BLOCK", "INELIGIBLE"):
                    block_n += 1
            if hold_n == 0 and block_n == 0:
                # Fallback: metadata counters when present
                hold_n = int(meta.get("holds") or meta.get("hold_count") or 0)
                block_n = int(meta.get("blocks") or meta.get("block_count") or 0)
        except Exception:
            pass

        import os

        # Derive symbols / top_candidates from the exact DecisionArtifactV2 just persisted.
        ledger_symbols, top_candidates = _ledger_symbols_and_candidates_from_artifact(artifact)
        eligible_from_ledger = len([r for r in ledger_symbols if r.get("verdict") == "ELIGIBLE"])
        shortlisted_from_ledger = len(
            [r for r in ledger_symbols if r.get("verdict") == "SHORTLISTED"]
        )
        ledger = EvaluationRunFull(
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            status="COMPLETED",
            duration_seconds=duration,
            total=int(meta.get("universe_size") or len(symbols) or len(ledger_symbols) or 0),
            evaluated=int(meta.get("evaluated_count_stage1") or len(ledger_symbols) or 0),
            eligible=int(meta.get("eligible_count") or eligible_from_ledger or 0),
            shortlisted=int(
                meta.get("shortlisted_count")
                or meta.get("eligible_count")
                or shortlisted_from_ledger
                or 0
            ),
            stage1_pass=int(meta.get("evaluated_count_stage1") or 0),
            stage2_pass=int(meta.get("evaluated_count_stage2") or 0),
            holds=hold_n,
            blocks=block_n,
            symbols=ledger_symbols,
            top_candidates=top_candidates,
            top_holds=top_holds,
            source=map_eval_trigger_to_source(active_trigger),
            engine="staged",
            correlation_id=run_id,
            market_phase=str(meta.get("market_phase") or "") or None,
            alerts=[
                {
                    "type": "PROVENANCE",
                    "trigger": active_trigger,
                    "allow_when_closed": bool(allow_when_closed),
                    "pid": os.getpid(),
                    "manual_only": True,
                    "trade_execution": False,
                }
            ],
            alerts_count=1,
        )
        try:
            save_run(ledger)
            update_latest_pointer(run_id, completed_at)
            logger.info(
                "[EVAL_COORD] ledger persisted run_id=%s symbols=%s eligible=%s top_candidates=%s",
                run_id,
                len(ledger_symbols),
                ledger.eligible,
                len(top_candidates),
            )
        except Exception:
            logger.exception("[EVAL_COORD] ledger persist failed run_id=%s", run_id)
            raise
        # R70.1 run-status contract:
        # - completed LIVE → daily summary + applicable candidate/lifecycle alerts
        # - failed LIVE → at most one DATA_HEALTH/SYSTEM failure notify (exception path)
        # - PAPER / rejected / skipped / lock-refused → no Slack
        if str(mode or "").strip().upper() == "LIVE":
            try:
                from app.core.alerts.alert_engine import process_run_completed

                process_run_completed(ledger)
            except Exception:
                logger.exception("[EVAL_COORD] alert processing failed run_id=%s (non-fatal)", run_id)
            # Options lifecycle UI notifications are emitted from evaluate_universe
            # via the artifact. Do not emit a second Slack-capable path here.
            # UI-store emit from_run is optional and must not call SlackNotifier.
            try:
                from app.core.alerts.options_lifecycle_notifications import (
                    emit_options_lifecycle_notifications_from_run,
                )

                emit_options_lifecycle_notifications_from_run(ledger)
            except Exception:
                logger.exception(
                    "[EVAL_COORD] options lifecycle notifications failed run_id=%s (non-fatal)",
                    run_id,
                )
        # R70 Final Closure Batch D: refresh Universe V2 after successful LIVE publish
        try:
            from app.core.universe_v2.builder import build_universe_v2_snapshot

            build_universe_v2_snapshot()
            logger.info("[EVAL_COORD] universe_v2 snapshot refreshed after run_id=%s", run_id)
        except Exception:
            logger.exception("[EVAL_COORD] universe_v2 refresh failed run_id=%s (non-fatal)", run_id)
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
        # Failed LIVE: at most one SYSTEM/DATA_HEALTH failure notification; never a
        # success EVAL_SUMMARY or trading SIGNAL. PAPER: no Slack.
        if str(mode or "").strip().upper() == "LIVE":
            try:
                from app.core.alerts.alert_engine import process_run_completed
                from app.core.eval.evaluation_store import load_run

                failed_ledger = load_run(run_id)
                if failed_ledger is not None:
                    process_run_completed(failed_ledger)
            except Exception:
                logger.exception(
                    "[EVAL_COORD] LIVE failure notification failed run_id=%s (non-fatal)",
                    run_id,
                )
        raise
    finally:
        end_universe_evaluation(run_id=run_id)
