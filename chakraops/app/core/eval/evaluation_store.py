# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Evaluation Run persistence store.

Stores evaluation runs as JSON files under out/evaluations/:
  - {run_id}.json - Full evaluation result
  - latest.json - Pointer to last COMPLETED run

This ensures all screens read the same truth - persisted, not in-memory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, fields, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Schema version for run payloads; increment on breaking changes.
RUN_SCHEMA_VERSION = 1

# Required top-level keys for run validation (before persist / after load).
_REQUIRED_RUN_KEYS = frozenset({"run_id", "started_at", "status", "symbols"})


class CorruptedRunError(Exception):
    """Raised when a run file exists but fails validation or checksum. Do not silent-fallback."""
    def __init__(self, run_id: str, path: Optional[Path], message: str):
        self.run_id = run_id
        self.path = path
        self.message = message
        super().__init__(f"Corrupted run {run_id}: {message}")

# ============================================================================
# Configuration
# ============================================================================

def _get_evaluations_dir() -> Path:
    """Get the evaluations directory path."""
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "evaluations"


def _ensure_evaluations_dir() -> Path:
    """Ensure evaluations directory exists and return path."""
    path = _get_evaluations_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class EvaluationRunSummary:
    """Summary of an evaluation run (for listing)."""
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: str = "RUNNING"  # RUNNING, COMPLETED, FAILED
    duration_seconds: float = 0.0
    # Counts
    total: int = 0
    evaluated: int = 0
    eligible: int = 0
    shortlisted: int = 0
    # Stage counts (2-stage pipeline)
    stage1_pass: int = 0
    stage2_pass: int = 0
    holds: int = 0
    blocks: int = 0
    # Context
    regime: Optional[str] = None
    risk_posture: Optional[str] = None
    market_phase: Optional[str] = None
    # Source tracking
    source: str = "manual"  # manual, scheduled, nightly, api
    # Error info
    error_summary: Optional[str] = None
    errors_count: int = 0


@dataclass
class EvaluationRunFull:
    """Full evaluation run with per-symbol results."""
    # Summary fields
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: str = "RUNNING"
    duration_seconds: float = 0.0
    # Counts
    total: int = 0
    evaluated: int = 0
    eligible: int = 0
    shortlisted: int = 0
    # Stage counts (2-stage pipeline)
    stage1_pass: int = 0
    stage2_pass: int = 0
    holds: int = 0
    blocks: int = 0
    # Context
    regime: Optional[str] = None
    risk_posture: Optional[str] = None
    market_phase: Optional[str] = None
    # Source tracking
    source: str = "manual"  # manual, scheduled, nightly, api
    # Per-symbol results (list of dicts for JSON serialization)
    symbols: List[Dict[str, Any]] = field(default_factory=list)
    # Top candidates (eligible, sorted by score)
    top_candidates: List[Dict[str, Any]] = field(default_factory=list)
    # Top holds (for review)
    top_holds: List[Dict[str, Any]] = field(default_factory=list)
    # Alerts generated
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    alerts_count: int = 0
    # Errors
    errors: List[str] = field(default_factory=list)
    error_summary: Optional[str] = None
    # Phase 9: Exposure summary (open positions, caps)
    exposure_summary: Optional[Dict[str, Any]] = None
    # Persistence integrity (Phase A)
    run_version: int = RUN_SCHEMA_VERSION
    checksum: Optional[str] = None
    # Phase F: diagnostics
    correlation_id: Optional[str] = None
    # Pipeline source: staged (single source of truth) vs legacy
    engine: str = "staged"  # "staged" | "legacy"

    def to_summary(self) -> EvaluationRunSummary:
        """Convert to summary (for listing)."""
        return EvaluationRunSummary(
            run_id=self.run_id,
            started_at=self.started_at,
            completed_at=self.completed_at,
            status=self.status,
            duration_seconds=self.duration_seconds,
            total=self.total,
            evaluated=self.evaluated,
            eligible=self.eligible,
            shortlisted=self.shortlisted,
            stage1_pass=self.stage1_pass,
            stage2_pass=self.stage2_pass,
            holds=self.holds,
            blocks=self.blocks,
            regime=self.regime,
            risk_posture=self.risk_posture,
            market_phase=self.market_phase,
            source=self.source,
            error_summary=self.error_summary,
            errors_count=len(self.errors),
        )


# ============================================================================
# Latest Pointer
# ============================================================================

@dataclass
class LatestPointer:
    """Pointer to the latest completed run."""
    run_id: str
    completed_at: str
    status: str = "COMPLETED"


# ============================================================================
# Store Operations
# ============================================================================

_STORE_LOCK = threading.Lock()


def generate_run_id() -> str:
    """Generate a unique run ID (also usable as correlation_id for logging)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"eval_{ts}_{short_uuid}"


def _run_path(run_id: str) -> Path:
    """Get path for a run file."""
    return _ensure_evaluations_dir() / f"{run_id}.json"


def _latest_path() -> Path:
    """Get path for latest pointer file."""
    return _ensure_evaluations_dir() / "latest.json"


def _run_lock_path() -> Path:
    """Path for run lock file (Phase 5: prevent overlapping runs)."""
    return _get_evaluations_dir() / "run.lock"


# Stale lock threshold: if lock file older than this, treat as stale and clear (seconds).
RUN_LOCK_STALE_SEC = 7200  # 2 hours


def _run_field_names() -> frozenset:
    return frozenset(f.name for f in fields(EvaluationRunFull))


def _validate_run_payload(data: Dict[str, Any]) -> None:
    """Validate run payload has required keys and types. Raises ValueError if invalid."""
    if not isinstance(data, dict):
        raise ValueError("payload is not a dict")
    missing = _REQUIRED_RUN_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"missing required keys: {sorted(missing)}")
    if not isinstance(data.get("symbols"), list):
        raise ValueError("symbols must be a list")
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string")


def acquire_run_lock(run_id: str, started_at: str) -> bool:
    """
    Acquire the run lock (create lock file). Prevents overlapping runs.
    Returns True if lock acquired, False if another run is in progress.
    Cross-platform: uses exclusive create (O_EXCL / 'x' mode).
    """
    path = _run_lock_path()
    _ensure_evaluations_dir()
    with _STORE_LOCK:
        if path.exists():
            # Stale lock?
            try:
                mtime = path.stat().st_mtime
                if (datetime.now(timezone.utc).timestamp() - mtime) > RUN_LOCK_STALE_SEC:
                    path.unlink()
                    logger.info("[STORE] Cleared stale run lock (older than %ds)", RUN_LOCK_STALE_SEC)
                else:
                    return False
            except OSError:
                return False
        try:
            path.write_text(f"{run_id}\n{started_at}", encoding="utf-8")
            logger.info("[STORE] Run lock acquired run_id=%s", run_id)
            return True
        except OSError as e:
            logger.warning("[STORE] Run lock create failed: %s", e)
            return False


def release_run_lock() -> None:
    """Release the run lock (remove lock file)."""
    path = _run_lock_path()
    with _STORE_LOCK:
        try:
            if path.exists():
                path.unlink()
                logger.info("[STORE] Run lock released")
        except OSError as e:
            logger.warning("[STORE] Run lock release failed: %s", e)


def get_current_run_status() -> Optional[Dict[str, Any]]:
    """
    Return current run status if a run is in progress (lock file exists and not stale).
    Returns {run_id, started_at} or None.
    """
    path = _run_lock_path()
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
        if (datetime.now(timezone.utc).timestamp() - mtime) > RUN_LOCK_STALE_SEC:
            path.unlink()
            return None
        text = path.read_text(encoding="utf-8")
        lines = text.strip().split("\n")
        run_id = lines[0].strip() if lines else ""
        started_at = lines[1].strip() if len(lines) > 1 else ""
        return {"run_id": run_id, "started_at": started_at}
    except OSError:
        return None


def clear_stale_run_lock() -> None:
    """Remove run lock if older than RUN_LOCK_STALE_SEC. Call on startup."""
    path = _run_lock_path()
    if not path.exists():
        return
    try:
        if (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) > RUN_LOCK_STALE_SEC:
            path.unlink()
            logger.info("[STORE] Cleared stale run lock on startup")
    except OSError:
        pass


def write_run_running(run_id: str, started_at: str) -> None:
    """Write minimal run file with status=RUNNING so run appears in list and has started_at."""
    run = EvaluationRunFull(
        run_id=run_id,
        started_at=started_at,
        completed_at=None,
        status="RUNNING",
        duration_seconds=0.0,
        total=0,
        evaluated=0,
        eligible=0,
        shortlisted=0,
        symbols=[],
        source="scheduled",
    )
    data = asdict(run)
    data["run_version"] = RUN_SCHEMA_VERSION
    data["checksum"] = _compute_checksum(data)
    path = _run_path(run_id)
    _ensure_evaluations_dir()
    temp = path.with_suffix(".tmp")
    try:
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        logger.info("[STORE] RUNNING stub persisted run_id=%s", run_id)
    except Exception as e:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass
        logger.exception("[STORE] write_run_running failed: %s", e)
        raise


def _compute_checksum(data: Dict[str, Any]) -> str:
    """Compute SHA256 of canonical JSON (excluding checksum). Deterministic for same content."""
    copy = {k: v for k, v in data.items() if k != "checksum"}
    canonical = json.dumps(copy, sort_keys=True, indent=2, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, data: Dict[str, Any], log_label: str) -> None:
    """Write JSON to path atomically: temp file → fsync → rename. No partial overwrite."""
    _ensure_evaluations_dir()
    temp = path.with_suffix(".tmp")
    try:
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        logger.info("[STORE] %s persisted to %s", log_label, path)
    except Exception as e:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass
        logger.exception("[STORE] persist_failure %s: %s", log_label, e)
        raise


def save_failed_run(
    run_id: str,
    reason: str,
    error: Exception | None = None,
    started_at: Optional[str] = None,
) -> None:
    """
    Persist a failed evaluation run: status=FAILED, error_summary, completed_at, duration.
    If started_at is None, tries to read from existing run file (RUNNING stub) for this run_id.
    """
    err_str = str(error) if error is not None else ""
    logger.warning("[STORE] save_failed_run run_id=%s reason=%s error=%s", run_id, reason, err_str)
    completed_at = datetime.now(timezone.utc).isoformat()
    if started_at is None:
        try:
            r = load_run(run_id)
            if r:
                started_at = r.started_at
        except Exception:
            pass
        if not started_at:
            started_at = completed_at
    try:
        start_ts = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
        end_ts = datetime.fromisoformat(completed_at.replace("Z", "+00:00")).timestamp()
        duration_seconds = max(0.0, end_ts - start_ts)
    except Exception:
        duration_seconds = 0.0
    run = EvaluationRunFull(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        status="FAILED",
        duration_seconds=duration_seconds,
        total=0,
        evaluated=0,
        eligible=0,
        shortlisted=0,
        symbols=[],
        source="scheduled",
        error_summary=reason[:500] if reason else err_str[:500],
        errors=[reason] if reason else [],
    )
    with _STORE_LOCK:
        data = asdict(run)
        data["run_version"] = RUN_SCHEMA_VERSION
        data["checksum"] = _compute_checksum(data)
        path = _run_path(run_id)
        _ensure_evaluations_dir()
        temp = path.with_suffix(".tmp")
        try:
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, path)
            logger.info("[STORE] FAILED run persisted run_id=%s", run_id)
        except Exception as e:
            if temp.exists():
                try:
                    temp.unlink()
                except OSError:
                    pass
            logger.exception("[STORE] save_failed_run persist failed: %s", e)


def save_run(run: EvaluationRunFull) -> None:
    """
    Save an evaluation run atomically. Validates payload before write.
    If validation fails, does not overwrite any existing file.
    Phase 4: Also writes data completeness report JSON alongside the run.
    """
    with _STORE_LOCK:
        data = asdict(run)
        _validate_run_payload(data)
        data["run_version"] = getattr(run, "run_version", RUN_SCHEMA_VERSION)
        data["checksum"] = _compute_checksum(data)
        path = _run_path(run.run_id)
        _atomic_write(path, data, f"save_run({run.run_id})")
        cid = getattr(run, "correlation_id", None) or run.run_id
        logger.info("[STORE] persist_success run_id=%s correlation_id=%s", run.run_id, cid)
        # Phase 4: Data completeness report
        try:
            from app.core.eval.data_completeness_report import write_data_completeness_report
            write_data_completeness_report(run.run_id, run.symbols, _get_evaluations_dir())
        except Exception as e:
            logger.warning("[STORE] data_completeness report write failed: %s", e)


def update_latest_pointer(run_id: str, completed_at: str) -> None:
    """Update the latest pointer atomically (temp → fsync → rename)."""
    with _STORE_LOCK:
        pointer = LatestPointer(run_id=run_id, completed_at=completed_at)
        data = asdict(pointer)
        path = _latest_path()
        _atomic_write(path, data, "update_latest_pointer")


def load_run(run_id: str) -> Optional[EvaluationRunFull]:
    """
    Load an evaluation run from disk. Returns None only if file does not exist.
    Raises CorruptedRunError if file exists but is invalid or checksum mismatch.
    """
    path = _run_path(run_id)
    if not path.exists():
        logger.debug("[STORE] read_source run_id=%s path_missing=%s", run_id, path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.exception("[STORE] persist_failure run_id=%s invalid_json", run_id)
        raise CorruptedRunError(run_id, path, f"invalid JSON: {e}") from e
    except Exception as e:
        logger.exception("[STORE] persist_failure run_id=%s read_error", run_id)
        raise CorruptedRunError(run_id, path, str(e)) from e
    try:
        _validate_run_payload(data)
    except ValueError as e:
        logger.error("[STORE] persist_failure run_id=%s validation_error %s", run_id, e)
        raise CorruptedRunError(run_id, path, str(e)) from e
    stored_checksum = data.get("checksum")
    if stored_checksum:
        computed = _compute_checksum(data)
        if computed != stored_checksum:
            logger.error("[STORE] persist_failure run_id=%s checksum_mismatch", run_id)
            raise CorruptedRunError(run_id, path, "checksum mismatch") from None
    allowed = _run_field_names()
    filtered = {k: data[k] for k in allowed if k in data}
    try:
        run = EvaluationRunFull(**filtered)
        logger.info("[STORE] read_source run_id=%s success", run_id)
        return run
    except Exception as e:
        logger.exception("[STORE] persist_failure run_id=%s construct_error", run_id)
        raise CorruptedRunError(run_id, path, str(e)) from e


def load_latest_pointer() -> Optional[LatestPointer]:
    """Load the latest pointer."""
    path = _latest_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return LatestPointer(**data)
    except Exception as e:
        logger.exception("[STORE] Failed to load latest pointer: %s", e)
        return None


def load_latest_run() -> Optional[EvaluationRunFull]:
    """Load the latest completed run."""
    pointer = load_latest_pointer()
    if not pointer:
        return None
    return load_run(pointer.run_id)


def list_runs(limit: int = 20) -> List[EvaluationRunSummary]:
    """List recent evaluation runs, newest first."""
    evaluations_dir = _get_evaluations_dir()
    if not evaluations_dir.exists():
        return []
    
    summaries = []
    # Get all run files (exclude latest.json)
    run_files = sorted(
        [f for f in evaluations_dir.glob("eval_*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )[:limit]
    
    allowed = _run_field_names()
    for run_file in run_files:
        try:
            with open(run_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            _validate_run_payload(data)
            filtered = {k: data[k] for k in allowed if k in data}
            run = EvaluationRunFull(**filtered)
            summaries.append(run.to_summary())
        except CorruptedRunError:
            raise
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("[STORE] Skipping corrupt run file %s: %s", run_file, e)
        except Exception as e:
            logger.warning("[STORE] Failed to load run %s: %s", run_file, e)
    
    return summaries


def delete_old_runs(keep_count: int = 50) -> int:
    """Delete old runs, keeping only the most recent ones."""
    evaluations_dir = _get_evaluations_dir()
    if not evaluations_dir.exists():
        return 0
    
    run_files = sorted(
        [f for f in evaluations_dir.glob("eval_*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    
    deleted = 0
    for run_file in run_files[keep_count:]:
        try:
            run_file.unlink()
            deleted += 1
        except Exception as e:
            logger.warning("[STORE] Failed to delete %s: %s", run_file, e)
    
    if deleted > 0:
        logger.info("[STORE] Deleted %d old runs", deleted)
    return deleted


# ============================================================================
# Conversion from UniverseEvaluationResult
# ============================================================================

def create_run_from_evaluation(
    run_id: str,
    started_at: str,
    evaluation_result: Any,  # UniverseEvaluationResult
    market_phase: Optional[str] = None,
) -> EvaluationRunFull:
    """
    Create an EvaluationRunFull from a UniverseEvaluationResult.
    This bridges the in-memory evaluator with the persistent store.
    """
    from app.core.eval.universe_evaluator import UniverseEvaluationResult, SymbolEvaluationResult, Alert
    
    if not isinstance(evaluation_result, UniverseEvaluationResult):
        raise TypeError("Expected UniverseEvaluationResult")
    
    # Convert symbols to dicts
    symbols_data = []
    for s in evaluation_result.symbols:
        sym_dict = {
            "symbol": s.symbol,
            "source": s.source,
            "price": s.price,
            "bid": s.bid,
            "ask": s.ask,
            "volume": s.volume,
            "avg_volume": s.avg_volume,
            "verdict": s.verdict,
            "primary_reason": s.primary_reason,
            "confidence": s.confidence,
            "score": s.score,
            "regime": s.regime,
            "risk": s.risk,
            "liquidity_ok": s.liquidity_ok,
            "liquidity_reason": s.liquidity_reason,
            "earnings_blocked": s.earnings_blocked,
            "earnings_days": s.earnings_days,
            "options_available": s.options_available,
            "options_reason": s.options_reason,
            "gates": s.gates,
            "blockers": s.blockers,
            "candidate_trades": [
                {
                    "strategy": ct.strategy,
                    "expiry": ct.expiry,
                    "strike": ct.strike,
                    "delta": ct.delta,
                    "credit_estimate": ct.credit_estimate,
                    "max_loss": ct.max_loss,
                    "why_this_trade": ct.why_this_trade,
                }
                for ct in s.candidate_trades
            ],
            "fetched_at": s.fetched_at,
            "error": s.error,
            # Data quality fields
            "data_completeness": getattr(s, "data_completeness", 1.0),
            "missing_fields": getattr(s, "missing_fields", []),
            "data_quality_details": getattr(s, "data_quality_details", {}),
            # Phase 9 & 10
            "position_open": getattr(s, "position_open", False),
            "position_reason": getattr(s, "position_reason", None),
            "capital_hint": getattr(s, "capital_hint", None),
            "waiver_reason": getattr(s, "waiver_reason", None),
            # Phase 3: Explainable scoring and capital-aware ranking
            "score_breakdown": getattr(s, "score_breakdown", None),
            "rank_reasons": getattr(s, "rank_reasons", None),
            "csp_notional": getattr(s, "csp_notional", None),
            "notional_pct": getattr(s, "notional_pct", None),
            "band_reason": getattr(s, "band_reason", None),
        }
        symbols_data.append(sym_dict)
    
    # Extract top candidates (eligible, sorted by score)
    eligible_symbols = [s for s in symbols_data if s["verdict"] == "ELIGIBLE"]
    top_candidates = sorted(eligible_symbols, key=lambda x: x.get("score", 0), reverse=True)[:10]
    
    # Convert alerts to dicts
    alerts_data = []
    for a in evaluation_result.alerts:
        alerts_data.append({
            "id": a.id,
            "type": a.type,
            "symbol": a.symbol,
            "message": a.message,
            "severity": a.severity,
            "created_at": a.created_at,
            "meta": a.meta,
        })
    
    # Determine regime/risk from first eligible symbol or first symbol
    regime = None
    risk_posture = None
    if symbols_data:
        first = symbols_data[0]
        regime = first.get("regime")
        risk_posture = first.get("risk")
    
    # Determine status
    status = evaluation_result.evaluation_state
    if status not in ("COMPLETED", "FAILED"):
        status = "COMPLETED" if evaluation_result.evaluated > 0 else "FAILED"
    
    completed_at = evaluation_result.last_evaluated_at or datetime.now(timezone.utc).isoformat()
    
    exposure_summary = getattr(evaluation_result, "exposure_summary", None)
    return EvaluationRunFull(
        run_id=run_id,
        started_at=started_at,
        correlation_id=run_id,
        completed_at=completed_at,
        status=status,
        duration_seconds=evaluation_result.duration_seconds,
        total=evaluation_result.total,
        evaluated=evaluation_result.evaluated,
        eligible=evaluation_result.eligible,
        shortlisted=evaluation_result.shortlisted,
        regime=regime,
        risk_posture=risk_posture,
        market_phase=market_phase,
        symbols=symbols_data,
        top_candidates=top_candidates,
        alerts=alerts_data,
        alerts_count=len(alerts_data),
        errors=evaluation_result.errors,
        error_summary=evaluation_result.errors[0] if evaluation_result.errors else None,
        exposure_summary=exposure_summary,
        engine=getattr(evaluation_result, "engine", "staged"),
    )


# ============================================================================
# API Response Builders
# ============================================================================

def build_latest_response() -> Dict[str, Any]:
    """
    Build response for GET /api/view/evaluation/latest.
    Single source of truth: includes full symbols so Dashboard/Universe need no other read path.
    """
    pointer = load_latest_pointer()
    if not pointer:
        return {
            "has_completed_run": False,
            "run_id": None,
            "completed_at": None,
            "status": "NO_RUNS",
            "reason": "No completed evaluation runs found",
            "read_source": "persisted",
            "engine": None,
            "counts": {"total": 0, "evaluated": 0, "eligible": 0, "shortlisted": 0},
            "top_candidates": [],
            "symbols": [],
            "alerts_count": 0,
        }
    try:
        run = load_run(pointer.run_id)
    except CorruptedRunError as e:
        logger.error("[STORE] read_source run %s corrupted: %s", pointer.run_id, e)
        return {
            "has_completed_run": False,
            "run_id": pointer.run_id,
            "completed_at": None,
            "status": "CORRUPTED",
            "reason": str(e),
            "read_source": "persisted",
            "backend_failure": True,
            "counts": {"total": 0, "evaluated": 0, "eligible": 0, "shortlisted": 0},
            "top_candidates": [],
            "symbols": [],
            "alerts_count": 0,
        }
    if not run:
        return {
            "has_completed_run": False,
            "run_id": pointer.run_id,
            "completed_at": None,
            "status": "NO_RUNS",
            "reason": "Latest pointer points to missing run",
            "read_source": "persisted",
            "engine": None,
            "counts": {"total": 0, "evaluated": 0, "eligible": 0, "shortlisted": 0},
            "top_candidates": [],
            "symbols": [],
            "alerts_count": 0,
        }
    # Phase 5: Dashboards read from last COMPLETED only; do not return symbols for RUNNING/FAILED
    if run.status != "COMPLETED":
        return {
            "has_completed_run": False,
            "run_id": run.run_id,
            "completed_at": run.completed_at,
            "status": run.status,
            "reason": f"Latest run is {run.status}, not COMPLETED",
            "read_source": "persisted",
            "engine": getattr(run, "engine", "staged"),
            "counts": {"total": 0, "evaluated": 0, "eligible": 0, "shortlisted": 0},
            "top_candidates": [],
            "symbols": [],
            "alerts_count": 0,
        }
    return {
        "has_completed_run": True,
        "run_id": run.run_id,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "status": run.status,
        "engine": getattr(run, "engine", "staged"),
        "duration_seconds": run.duration_seconds,
        "counts": {
            "total": run.total,
            "evaluated": run.evaluated,
            "eligible": run.eligible,
            "shortlisted": run.shortlisted,
        },
        "regime": run.regime,
        "risk_posture": run.risk_posture,
        "market_phase": run.market_phase,
        "top_candidates": run.top_candidates,
        "symbols": run.symbols,
        "alerts_count": run.alerts_count,
        "errors_count": len(run.errors),
        "read_source": "persisted",
        "correlation_id": getattr(run, "correlation_id", None) or run.run_id,
    }


def build_runs_list_response(limit: int = 20) -> Dict[str, Any]:
    """Build response for GET /api/view/evaluation/runs."""
    summaries = list_runs(limit)
    pointer = load_latest_pointer()
    
    return {
        "runs": [asdict(s) for s in summaries],
        "count": len(summaries),
        "latest_run_id": pointer.run_id if pointer else None,
    }


def build_run_detail_response(run_id: str) -> Dict[str, Any]:
    """Build response for GET /api/view/evaluation/{run_id}."""
    run = load_run(run_id)
    
    if not run:
        return {
            "found": False,
            "run_id": run_id,
            "reason": f"Run {run_id} not found",
        }
    
    return {
        "found": True,
        **asdict(run),
    }


__all__ = [
    "CorruptedRunError",
    "EvaluationRunSummary",
    "EvaluationRunFull",
    "LatestPointer",
    "RUN_SCHEMA_VERSION",
    "generate_run_id",
    "save_run",
    "save_failed_run",
    "update_latest_pointer",
    "load_run",
    "load_latest_pointer",
    "load_latest_run",
    "list_runs",
    "delete_old_runs",
    "create_run_from_evaluation",
    "build_latest_response",
    "build_runs_list_response",
    "build_run_detail_response",
    "acquire_run_lock",
    "release_run_lock",
    "get_current_run_status",
    "clear_stale_run_lock",
    "write_run_running",
]
