# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.2: Sanity Check Runner — run diagnostics, persist to out/diagnostics_history.jsonl."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

ALL_CHECKS = {"orats", "decision_store", "universe", "positions", "scheduler", "portfolio_risk"}
_RETENTION_LINES = 5000  # Phase 8.6
_APPEND_LOCK = threading.Lock()


def _diagnostics_history_path() -> Path:
    """Append-only file under out/diagnostics_history.jsonl."""
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[2] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "diagnostics_history.jsonl"


def _prune_diagnostics_if_needed(path: Path) -> None:
    """If file exceeds _RETENTION_LINES, rewrite with last N lines (atomic)."""
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if len(lines) <= _RETENTION_LINES:
        return
    kept = lines[-_RETENTION_LINES:]
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="diagnostics_history.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ln in kept:
                f.write(ln + "\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def _append_run(result: Dict[str, Any]) -> None:
    """Append one run result as a JSON line. Phase 8.6: prune to last N lines."""
    path = _diagnostics_history_path()
    line = json.dumps(result, default=str) + "\n"
    with _APPEND_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        _prune_diagnostics_if_needed(path)


def _load_history(limit: int = 10) -> List[Dict[str, Any]]:
    """Load last N runs (newest first)."""
    path = _diagnostics_history_path()
    if not path.exists():
        return []
    lines: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                lines.append(s)
    out: List[Dict[str, Any]] = []
    for s in reversed(lines[-limit:]):
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            pass
    return out


def _run_orats_check() -> Dict[str, Any]:
    """ORATS probe: status, latency_ms, last_success_at."""
    start = time.perf_counter()
    try:
        from app.api.data_health import get_data_health
        dh = get_data_health()
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        status_raw = (dh.get("status") or "UNKNOWN").upper()
        if status_raw in ("OK",):
            status = "PASS"
        elif status_raw in ("WARN", "DEGRADED"):
            status = "WARN"
        else:
            status = "FAIL"
        return {
            "check": "orats",
            "status": status,
            "details": {
                "status": status_raw,
                "latency_ms": elapsed_ms,
                "last_success_at": dh.get("last_success_at") or dh.get("effective_last_success_at"),
                "last_error_reason": dh.get("last_error_reason"),
            },
        }
    except Exception as e:
        return {
            "check": "orats",
            "status": "FAIL",
            "details": {"error": str(e)},
        }


def _run_decision_store_check() -> Dict[str, Any]:
    """Decision store read + artifact metadata (pipeline_timestamp, active_path)."""
    try:
        from app.core.eval.evaluation_store_v2 import (
            get_evaluation_store_v2,
            get_decision_store_path,
            get_active_decision_path,
        )
        from app.market.market_hours import get_market_phase
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        artifact = store.get_latest()
        store_path = get_decision_store_path()
        phase = get_market_phase() or "UNKNOWN"
        active_path = get_active_decision_path(phase)
        if artifact is None or not active_path.exists():
            return {
                "check": "decision_store",
                "status": "FAIL",
                "details": {"reason": "No artifact or active path missing", "active_path": str(active_path)},
            }
        meta = artifact.metadata or {}
        pipeline_ts = meta.get("pipeline_timestamp")
        return {
            "check": "decision_store",
            "status": "PASS",
            "details": {
                "pipeline_timestamp": pipeline_ts,
                "active_path": str(active_path),
                "canonical_path": str(store_path),
                "symbol_count": len(artifact.symbols) if artifact.symbols else 0,
            },
        }
    except Exception as e:
        return {
            "check": "decision_store",
            "status": "FAIL",
            "details": {"error": str(e)},
        }


def _run_universe_check() -> Dict[str, Any]:
    """Universe read: count, sample symbol fields."""
    try:
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        artifact = store.get_latest()
        if artifact is None or not artifact.symbols:
            return {
                "check": "universe",
                "status": "WARN",
                "details": {"count": 0, "reason": "No symbols in artifact"},
            }
        count = len(artifact.symbols)
        sample = artifact.symbols[0] if artifact.symbols else None
        sample_fields = {}
        if sample:
            sample_fields = {
                "symbol": getattr(sample, "symbol", None),
                "verdict": getattr(sample, "verdict", None),
                "score": getattr(sample, "score", None),
            }
        return {
            "check": "universe",
            "status": "PASS" if count > 0 else "WARN",
            "details": {"count": count, "sample": sample_fields},
        }
    except Exception as e:
        return {
            "check": "universe",
            "status": "FAIL",
            "details": {"error": str(e)},
        }


def _run_positions_check() -> Dict[str, Any]:
    """Positions GET/POST roundtrip using paper account.
    Phase 8.6: Unique run_id tag, guaranteed cleanup in finally, no pollution.
    """
    run_id = f"DIAG_TEST_{uuid.uuid4().hex[:12]}"
    test_symbol = "DIAG_TEST"
    created_position_id: Optional[str] = None
    try:
        from app.core.positions.service import list_positions, add_paper_position
        before = list_positions(status=None, symbol=None)
        before_ids = {p.position_id for p in before}
        pos, errs, _ = add_paper_position({
            "symbol": test_symbol,
            "strategy": "CSP",
            "contracts": 1,
            "strike": 100.0,
            "expiration": "2026-12-20",
            "credit_expected": 1.0,
            "contract_key": "100-2026-12-20-PUT",
            "notes": run_id,
        })
        if errs or pos is None:
            return {
                "check": "positions",
                "status": "FAIL",
                "details": {"error": "; ".join(errs) if errs else "Failed to create paper position"},
            }
        created_position_id = pos.position_id
        after = list_positions(status=None, symbol=None)
        found = any(p.symbol == test_symbol and p.position_id == pos.position_id for p in after)
        if found:
            return {
                "check": "positions",
                "status": "PASS",
                "details": {"get_post_roundtrip": "OK", "created_id": pos.position_id},
            }
        return {
            "check": "positions",
            "status": "FAIL",
            "details": {"reason": "POST succeeded but GET did not return created position"},
        }
    except Exception as e:
        return {
            "check": "positions",
            "status": "FAIL",
            "details": {"error": str(e)},
        }
    finally:
        # Guaranteed cleanup: always close/remove DIAG_TEST positions we created
        if created_position_id:
            try:
                from app.core.positions.store import update_position
                update_position(
                    created_position_id,
                    {"status": "CLOSED", "closed_at": datetime.now(timezone.utc).isoformat()},
                )
            except Exception as cleanup_err:
                logger.warning("[DIAGNOSTICS] Positions check cleanup failed for %s: %s", created_position_id, cleanup_err)
        # Also close any other open DIAG_TEST positions from prior failed runs
        try:
            from app.core.positions.store import list_positions, update_position
            all_pos = list_positions(status=None, symbol=test_symbol)
            for p in all_pos:
                if p.status in ("OPEN", "PARTIAL_EXIT") and (p.notes or "").startswith("DIAG_TEST_"):
                    try:
                        update_position(
                            p.position_id,
                            {"status": "CLOSED", "closed_at": datetime.now(timezone.utc).isoformat()},
                        )
                    except Exception:
                        pass
        except Exception:
            pass


def _run_portfolio_risk_check() -> Dict[str, Any]:
    """Phase 14.0: Evaluate portfolio risk against account limits. Emit notification on FAIL/WARN."""
    try:
        from app.core.accounts.store import get_default_account
        from app.core.positions.service import list_positions
        from app.core.portfolio.risk import evaluate_portfolio_risk
        from app.api.notifications_store import append_notification

        account = get_default_account()
        if account is None:
            return {
                "check": "portfolio_risk",
                "status": "PASS",
                "details": {"reason": "No default account; skip"},
            }
        positions = list_positions(status=None, symbol=None, exclude_test=True)
        open_pos = [p for p in positions if (p.status or "").upper() in ("OPEN", "PARTIAL_EXIT")]
        result = evaluate_portfolio_risk(account, open_pos)
        status = result.get("status", "PASS")
        breaches = result.get("breaches") or []
        details = {
            "account_id": account.account_id,
            "status": status,
            "metrics": result.get("metrics", {}),
            "breach_count": len(breaches),
            "breaches": breaches[:10],  # Limit in details
        }
        check_result = {"check": "portfolio_risk", "status": status, "details": details}
        if status in ("FAIL", "WARN") and breaches:
            severity = "ERROR" if status == "FAIL" else "WARN"
            summary = "; ".join(b.get("message", "") for b in breaches[:5])
            append_notification(
                severity=severity,
                ntype="PORTFOLIO_RISK",
                message=summary[:500] or "Portfolio risk limit breach",
                symbol=None,
                details={"breaches": breaches, "metrics": result.get("metrics", {})},
                subtype="RISK_LIMIT_BREACH",
            )
        return check_result
    except Exception as e:
        return {
            "check": "portfolio_risk",
            "status": "FAIL",
            "details": {"error": str(e)},
        }


def _run_scheduler_check(app_start_time_utc: Optional[float] = None) -> Dict[str, Any]:
    """Scheduler: next_run_at present; last_run_at within expected window when market open.
    Phase 8.6: Market-hours gating — when market closed, return PASS (no false WARN).
    Restart grace — when within 10 min of app start, do not report scheduler missed.
    """
    try:
        from app.api.server import get_scheduler_status, get_app_start_time_utc
        from app.market.market_hours import get_market_phase, is_market_open
        from app.core.system.watchdog import RESTART_GRACE_MINUTES
        sched = get_scheduler_status()
        next_run_at = sched.get("next_run_at")
        last_run_at = sched.get("last_run_at")
        interval_min = sched.get("interval_minutes") or 30
        market_open = is_market_open()
        phase = get_market_phase() or "UNKNOWN"
        start_utc = app_start_time_utc if app_start_time_utc is not None else get_app_start_time_utc()
        in_grace = False
        if start_utc is not None:
            elapsed_min = (datetime.now(timezone.utc).timestamp() - start_utc) / 60
            in_grace = elapsed_min < RESTART_GRACE_MINUTES
        # Market closed or in restart grace: skip WARN/FAIL (return PASS with note)
        if not market_open or in_grace:
            return {
                "check": "scheduler",
                "status": "PASS",
                "details": {
                    "next_run_at": next_run_at,
                    "last_run_at": last_run_at,
                    "market_open": market_open,
                    "phase": phase,
                    "note": "market closed" if not market_open else "restart grace window",
                },
            }
        if next_run_at is None and last_run_at is None:
            return {
                "check": "scheduler",
                "status": "WARN",
                "details": {"reason": "No last_run_at or next_run_at yet", "market_open": market_open},
            }
        if next_run_at is None:
            return {
                "check": "scheduler",
                "status": "WARN",
                "details": {"reason": "next_run_at missing", "last_run_at": last_run_at},
            }
        window_ok = True
        if last_run_at:
            try:
                last_dt = datetime.fromisoformat(last_run_at.replace("Z", "+00:00"))
                max_age = timedelta(minutes=interval_min * 2)
                if datetime.now(timezone.utc) - last_dt > max_age:
                    window_ok = False
            except (ValueError, TypeError):
                window_ok = False
        status = "PASS" if window_ok else "WARN"
        return {
            "check": "scheduler",
            "status": status,
            "details": {
                "next_run_at": next_run_at,
                "last_run_at": last_run_at,
                "market_open": market_open,
                "phase": phase,
                "within_window": window_ok,
            },
        }
    except Exception as e:
        return {
            "check": "scheduler",
            "status": "FAIL",
            "details": {"error": str(e)},
        }


CHECK_FNS = {
    "orats": _run_orats_check,
    "decision_store": _run_decision_store_check,
    "universe": _run_universe_check,
    "positions": _run_positions_check,
    "portfolio_risk": _run_portfolio_risk_check,
    "scheduler": _run_scheduler_check,
}


def run_diagnostics(checks: Optional[Set[str]] = None) -> Dict[str, Any]:
    """
    Run requested checks (default: all).
    Persist result to out/diagnostics_history.jsonl.
    Returns { timestamp_utc, checks: [{ check, status, details }], overall_status }.
    """
    to_run = (checks or ALL_CHECKS) & ALL_CHECKS
    if not to_run:
        to_run = ALL_CHECKS
    now = datetime.now(timezone.utc).isoformat()
    results: List[Dict[str, Any]] = []
    for name in sorted(to_run):
        fn = CHECK_FNS.get(name)
        if fn:
            try:
                results.append(fn())
            except Exception as e:
                results.append({"check": name, "status": "FAIL", "details": {"error": str(e)}})
    fails = sum(1 for r in results if r.get("status") == "FAIL")
    warns = sum(1 for r in results if r.get("status") == "WARN")
    if fails > 0:
        overall = "FAIL"
    elif warns > 0:
        overall = "WARN"
    else:
        overall = "PASS"
    out = {
        "timestamp_utc": now,
        "checks": results,
        "overall_status": overall,
    }
    _append_run(out)
    logger.info("[DIAGNOSTICS] Run completed: overall=%s, checks=%s", overall, [r.get("check") for r in results])
    return out


def get_diagnostics_history(limit: int = 10) -> List[Dict[str, Any]]:
    """Return last N runs (newest first)."""
    return _load_history(limit=limit)
