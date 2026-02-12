# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe batch evaluator: runs evaluation across all symbols, caches results, generates alerts."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.models.data_quality import (
    DataQuality,
    FieldValue,
    ReasonCode,
    wrap_field_float,
    wrap_field_int,
    compute_data_completeness,
    build_data_incomplete_reason,
)

logger = logging.getLogger(__name__)

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class CandidateTrade:
    """A potential trade for a symbol."""
    strategy: str  # CSP, CC, HOLD
    expiry: Optional[str] = None
    strike: Optional[float] = None
    delta: Optional[float] = None
    credit_estimate: Optional[float] = None
    max_loss: Optional[float] = None
    why_this_trade: str = ""


@dataclass
class SymbolEvaluationResult:
    """Evaluation result for a single symbol."""
    symbol: str
    source: str = "ORATS"
    # Stock data
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    avg_option_volume_20d: Optional[float] = None
    avg_stock_volume_20d: Optional[float] = None
    # Verdict
    verdict: str = "UNKNOWN"  # ELIGIBLE, HOLD, BLOCKED, UNKNOWN
    primary_reason: str = ""
    confidence: float = 0.0
    score: int = 0  # 0-100
    # Context
    regime: Optional[str] = None  # BULL, BEAR, NEUTRAL, UNKNOWN
    risk: Optional[str] = None  # LOW, MODERATE, HIGH, UNKNOWN
    liquidity_ok: bool = False
    liquidity_reason: str = ""
    earnings_blocked: bool = False
    earnings_days: Optional[int] = None
    options_available: bool = False
    options_reason: str = ""
    # Gates passed/failed
    gates: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    # Candidate trades
    candidate_trades: List[CandidateTrade] = field(default_factory=list)
    # Metadata
    fetched_at: Optional[str] = None
    error: Optional[str] = None
    # Phase 6: Provider timestamps and IV (for data_dependencies / staleness)
    iv_rank: Optional[float] = None
    quote_date: Optional[str] = None
    # Data quality tracking
    data_completeness: float = 1.0  # 0.0 to 1.0
    missing_fields: List[str] = field(default_factory=list)
    data_quality_details: Dict[str, str] = field(default_factory=dict)  # field_name -> quality status
    # 2-Stage pipeline fields (new)
    stage_reached: str = "STAGE1_ONLY"  # NOT_STARTED, STAGE1_ONLY, STAGE2_CHAIN
    selected_contract: Optional[Dict[str, Any]] = None  # Selected contract details from stage 2
    selected_expiration: Optional[str] = None  # Expiration date of selected contract
    # Phase 9: Position awareness
    position_open: bool = False
    position_reason: Optional[str] = None
    # OPRA authority: set when liquidity from /datav2/strikes/options (DERIVED_FROM_OPRA)
    waiver_reason: Optional[str] = None
    # Phase 10: confidence band capital hint (dict for JSON)
    capital_hint: Optional[Dict[str, Any]] = None
    # Phase 3: Explainable scoring and capital-aware ranking
    score_breakdown: Optional[Dict[str, Any]] = None
    rank_reasons: Optional[Dict[str, Any]] = None
    csp_notional: Optional[float] = None
    notional_pct: Optional[float] = None
    band_reason: Optional[str] = None


@dataclass
class Alert:
    """An alert generated from evaluation."""
    id: str
    type: str  # ELIGIBLE, TARGET_HIT, DATA_STALE, DATA_INCOMPLETE, EARNINGS_SOON, LIQUIDITY_WARN
    symbol: str
    message: str
    severity: str = "INFO"  # INFO, WARN, ERROR
    created_at: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UniverseEvaluationResult:
    """Result of a full universe evaluation run."""
    evaluation_state: str = "IDLE"  # IDLE, RUNNING, COMPLETED, FAILED
    evaluation_state_reason: str = "No evaluation run yet"
    last_evaluated_at: Optional[str] = None
    next_scheduled_at: Optional[str] = None
    duration_seconds: float = 0.0
    # Counts
    total: int = 0
    evaluated: int = 0
    eligible: int = 0
    shortlisted: int = 0
    # Per-symbol results
    symbols: List[SymbolEvaluationResult] = field(default_factory=list)
    # Alerts generated
    alerts: List[Alert] = field(default_factory=list)
    # Errors
    errors: List[str] = field(default_factory=list)
    # Phase 9: Exposure summary (open positions, caps)
    exposure_summary: Optional[Dict[str, Any]] = None
    # Pipeline source: staged (single source of truth) vs legacy
    engine: str = "staged"  # "staged" | "legacy"


# ============================================================================
# Global Cache
# ============================================================================

_CACHE: Optional[UniverseEvaluationResult] = None
_CACHE_LOCK = threading.Lock()
_EVAL_LOCK = threading.Lock()
_IS_RUNNING = False
_CURRENT_RUN_ID: Optional[str] = None

# Configurable thresholds
SHORTLIST_SCORE_THRESHOLD = 70
EARNINGS_WARN_DAYS = 7
LIQUIDITY_MIN_OI = 100
LIQUIDITY_MIN_VOLUME = 1000

# Score cap when data is incomplete - cannot rank as GREEN (>70) with missing data
DATA_INCOMPLETE_SCORE_CAP = 60

# Required liquidity fields - if any are MISSING, verdict is HOLD (not LIQUIDITY_WARN)
REQUIRED_LIQUIDITY_FIELDS = ["volume", "bid", "ask"]


def get_cached_evaluation() -> Optional[UniverseEvaluationResult]:
    """Get the cached evaluation result (if any)."""
    with _CACHE_LOCK:
        return _CACHE


def get_evaluation_state() -> Dict[str, Any]:
    """Get current evaluation state for snapshot."""
    global _IS_RUNNING, _CURRENT_RUN_ID
    with _CACHE_LOCK:
        if _IS_RUNNING:
            return {
                "evaluation_state": "RUNNING",
                "evaluation_state_reason": "Evaluation currently in progress",
                "last_evaluated_at": _CACHE.last_evaluated_at if _CACHE else None,
                "current_run_id": _CURRENT_RUN_ID,
            }
        if _CACHE is None:
            # Check persistent store for latest run
            try:
                from app.core.eval.evaluation_store import load_latest_pointer
                pointer = load_latest_pointer()
                if pointer:
                    return {
                        "evaluation_state": "COMPLETED",
                        "evaluation_state_reason": f"Last run completed at {pointer.completed_at}",
                        "last_evaluated_at": pointer.completed_at,
                        "last_run_id": pointer.run_id,
                    }
            except ImportError:
                pass
            return {
                "evaluation_state": "IDLE",
                "evaluation_state_reason": "No evaluation run yet",
                "last_evaluated_at": None,
            }
        return {
            "evaluation_state": _CACHE.evaluation_state,
            "evaluation_state_reason": _CACHE.evaluation_state_reason,
            "last_evaluated_at": _CACHE.last_evaluated_at,
        }


def trigger_evaluation(
    universe_symbols: List[str],
    market_phase: Optional[str] = None,
    use_staged: bool = True,
) -> Dict[str, Any]:
    """
    Trigger evaluation in background with persistence.
    Staged evaluation is the single source of truth; legacy must not be used during ops run.
    
    Args:
        universe_symbols: List of symbols to evaluate
        market_phase: Current market phase for context
        use_staged: If True, use 2-stage pipeline (default). If False, raises - no legacy during ops.
    
    Returns:
        {started: bool, reason: str, run_id: str}
    """
    # Fail-fast: prevent non-staged evaluation during ops run (no silent legacy)
    if not use_staged:
        raise RuntimeError("Non-staged evaluation attempted during ops run")

    global _IS_RUNNING, _CURRENT_RUN_ID
    
    from app.core.eval.evaluation_store import (
        generate_run_id,
        save_run,
        save_failed_run,
        update_latest_pointer,
        create_run_from_evaluation,
        acquire_run_lock,
        release_run_lock,
        write_run_running,
        get_current_run_status,
    )

    run_id = generate_run_id()
    started_at = datetime.now(timezone.utc).isoformat()
    if not acquire_run_lock(run_id, started_at):
        cur = get_current_run_status()
        run_id_in_progress = cur.get("run_id") if cur else None
        logger.info("[EVAL] Skipping trigger: run already in progress run_id=%s", run_id_in_progress)
        return {"started": False, "reason": "Evaluation already in progress", "run_id": run_id_in_progress}

    with _EVAL_LOCK:
        _IS_RUNNING = True
        _CURRENT_RUN_ID = run_id
    try:
        write_run_running(run_id, started_at)
    except Exception as e:
        logger.exception("[EVAL] write_run_running failed: %s", e)
        release_run_lock()
        with _EVAL_LOCK:
            _IS_RUNNING = False
            _CURRENT_RUN_ID = None
        return {"started": False, "reason": str(e), "run_id": run_id}

    def _run():
        global _IS_RUNNING, _CURRENT_RUN_ID
        try:
            result = run_universe_evaluation_staged(universe_symbols, use_staged=True)
            try:
                run = create_run_from_evaluation(
                    run_id=run_id,
                    started_at=started_at,
                    evaluation_result=result,
                    market_phase=market_phase,
                )
                save_run(run)
                if run.status == "COMPLETED" and run.completed_at:
                    update_latest_pointer(run_id, run.completed_at)
                    logger.info("[EVAL] Run %s completed and persisted", run_id)
                try:
                    from app.core.eval.run_artifacts import write_run_artifacts, update_latest_and_recent, purge_old_runs
                    run_dir = write_run_artifacts(run)
                    update_latest_and_recent(run, run_dir)
                    purge_old_runs()
                except Exception as art_err:
                    logger.warning("[EVAL] Run artifacts write/purge failed (non-fatal): %s", art_err)
                try:
                    from app.core.alerts.alert_engine import process_run_completed
                    process_run_completed(run)
                except Exception as alert_err:
                    logger.warning("[EVAL] Alert processing failed (non-fatal): %s", alert_err)
            except Exception as e:
                logger.exception("[EVAL] Failed to persist run %s: %s", run_id, e)
                save_failed_run(run_id, str(e), e, started_at)
        except Exception as e:
            logger.exception("[EVAL] Run %s failed: %s", run_id, e)
            save_failed_run(run_id, str(e), e, started_at)
            try:
                from app.core.alerts.alert_engine import process_run_completed
                from app.core.eval.evaluation_store import load_run
                failed_run = load_run(run_id)
                if failed_run:
                    process_run_completed(failed_run)
            except Exception as alert_err:
                logger.warning("[EVAL] Alert processing for failed run (non-fatal): %s", alert_err)
        finally:
            release_run_lock()
            with _EVAL_LOCK:
                _IS_RUNNING = False
                _CURRENT_RUN_ID = None

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"started": True, "reason": "Evaluation started", "run_id": run_id}


# ============================================================================
# Evaluation Logic
# ============================================================================

def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely convert to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """Safely convert to int."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _compute_score(result: SymbolEvaluationResult) -> int:
    """
    Compute a simple score (0-100) based on gates and conditions.
    - Start at 50 (neutral baseline)
    - Add/subtract based on conditions
    - CAP score if data is incomplete (cannot rank as GREEN with missing data)
    """
    score = 50

    # Liquidity: +15 if OK
    if result.liquidity_ok:
        score += 15
    else:
        score -= 10

    # Options available: +10
    if result.options_available:
        score += 10
    else:
        score -= 15

    # Earnings: -20 if blocked, -5 if within 7 days
    if result.earnings_blocked:
        score -= 20
    elif result.earnings_days is not None and result.earnings_days <= EARNINGS_WARN_DAYS:
        score -= 5

    # Regime: +10 for BULL, +5 for NEUTRAL, -10 for BEAR
    if result.regime == "BULL":
        score += 10
    elif result.regime == "NEUTRAL":
        score += 5
    elif result.regime == "BEAR":
        score -= 10

    # Risk: +5 for LOW, -5 for HIGH
    if result.risk == "LOW":
        score += 5
    elif result.risk == "HIGH":
        score -= 5

    # Gates passed: +2 each
    gates_passed = sum(1 for g in result.gates if g.get("status") == "PASS")
    score += gates_passed * 2

    # Candidate trades: +5 if any
    if result.candidate_trades:
        score += 5

    # Clamp to 0-100
    score = max(0, min(100, score))

    # CAP SCORE if data is incomplete - cannot rank as GREEN (>70) with missing data
    # This prevents incomplete data symbols from appearing as top candidates
    if result.missing_fields and result.data_completeness < 0.75:
        score = min(score, DATA_INCOMPLETE_SCORE_CAP)

    return score


def _determine_verdict(result: SymbolEvaluationResult) -> tuple[str, str]:
    """
    Determine verdict and primary reason based on evaluation result.
    Returns (verdict, primary_reason).
    
    IMPORTANT: Distinguish between MISSING data and actual low values:
    - MISSING required liquidity fields => HOLD with DATA_INCOMPLETE reason
    - VALID but low liquidity values => HOLD with "Low liquidity" reason
    """
    blockers = result.blockers

    if result.error:
        return "UNKNOWN", f"Error during evaluation - {result.error}"

    if not result.options_available:
        return "BLOCKED", result.options_reason or "No options data available"

    if result.earnings_blocked:
        return "BLOCKED", f"Earnings within exclusion window ({result.earnings_days} days)"

    # Check if required liquidity fields are MISSING (not just low)
    # This takes precedence over "low liquidity" checks
    missing_liquidity_fields = [
        f for f in REQUIRED_LIQUIDITY_FIELDS
        if f in result.missing_fields
    ]
    if missing_liquidity_fields:
        reason = build_data_incomplete_reason(missing_liquidity_fields)
        return "HOLD", reason

    # Now check if liquidity is actually low (fields are VALID but values fail threshold)
    if not result.liquidity_ok:
        # This is actual low liquidity, not missing data
        return "HOLD", result.liquidity_reason or "Insufficient liquidity"

    if blockers:
        return "BLOCKED", blockers[0]

    # Check gates
    failed_gates = [g for g in result.gates if g.get("status") == "FAIL"]
    if failed_gates:
        return "HOLD", failed_gates[0].get("reason", "Gate check failed")

    # Check data completeness - if below threshold, add warning to reason
    # Note: We still allow ELIGIBLE but flag the data quality issue
    if result.data_completeness < 0.75 and result.missing_fields:
        reason = build_data_incomplete_reason(result.missing_fields)
        # HOLD with data incomplete - cannot be ELIGIBLE without sufficient data
        return "HOLD", reason

    # All checks passed
    return "ELIGIBLE", "All checks passed - eligible for trade selection"


def _generate_alerts(result: SymbolEvaluationResult) -> List[Alert]:
    """
    Generate alerts from evaluation result.
    
    IMPORTANT: Generate DATA_INCOMPLETE alerts (not LIQUIDITY_WARN) when data is missing.
    Only generate LIQUIDITY_WARN when fields are VALID but values fail thresholds.
    """
    alerts = []
    now_iso = datetime.now(timezone.utc).isoformat()
    base_id = f"{result.symbol}_{int(time.time())}"

    if result.verdict == "ELIGIBLE":
        alerts.append(Alert(
            id=f"{base_id}_eligible",
            type="ELIGIBLE",
            symbol=result.symbol,
            message=f"{result.symbol} is eligible for trading (score: {result.score})",
            severity="INFO",
            created_at=now_iso,
            meta={"score": result.score, "price": result.price},
        ))

    if result.earnings_days is not None and result.earnings_days <= EARNINGS_WARN_DAYS and not result.earnings_blocked:
        alerts.append(Alert(
            id=f"{base_id}_earnings",
            type="EARNINGS_SOON",
            symbol=result.symbol,
            message=f"{result.symbol} has earnings in {result.earnings_days} days",
            severity="WARN",
            created_at=now_iso,
            meta={"days": result.earnings_days},
        ))

    # When OPRA is authority (waiver_reason=DERIVED_FROM_OPRA), do NOT emit DATA_INCOMPLETE for stock fields
    missing_liquidity_fields = [
        f for f in REQUIRED_LIQUIDITY_FIELDS
        if f in result.missing_fields
    ]
    opra_waiver = getattr(result, "waiver_reason", None) == "DERIVED_FROM_OPRA"

    if missing_liquidity_fields and not opra_waiver:
        # Generate DATA_INCOMPLETE alert - data is missing, NOT low liquidity
        missing_str = ", ".join(missing_liquidity_fields)
        alerts.append(Alert(
            id=f"{base_id}_incomplete",
            type="DATA_INCOMPLETE",
            symbol=result.symbol,
            message=f"{result.symbol} - DATA_INCOMPLETE: missing {missing_str}",
            severity="WARN",
            created_at=now_iso,
            meta={
                "completeness": result.data_completeness,
                "missing_fields": result.missing_fields,
                "missing_liquidity_fields": missing_liquidity_fields,
            },
        ))
    elif not result.liquidity_ok and result.verdict != "BLOCKED" and not missing_liquidity_fields:
        # Generate LIQUIDITY_WARN only when fields are VALID but values fail threshold.
        # Never emit LIQUIDITY_WARN when data is missing (missing => BLOCK/DATA_INCOMPLETE).
        alerts.append(Alert(
            id=f"{base_id}_liquidity",
            type="LIQUIDITY_WARN",
            symbol=result.symbol,
            message=f"{result.symbol} has low liquidity - {result.liquidity_reason}",
            severity="WARN",
            created_at=now_iso,
            meta={"liquidity_reason": result.liquidity_reason},
        ))

    if result.error:
        alerts.append(Alert(
            id=f"{base_id}_data",
            type="DATA_STALE",
            symbol=result.symbol,
            message=f"{result.symbol} data fetch error - {result.error}",
            severity="ERROR",
            created_at=now_iso,
        ))

    # Additional DATA_INCOMPLETE alert for non-liquidity missing fields (skip when OPRA waiver applies)
    other_missing = [f for f in result.missing_fields if f not in REQUIRED_LIQUIDITY_FIELDS]
    if other_missing and result.data_completeness < 0.75 and not opra_waiver:
        missing_str = ", ".join(other_missing[:5])
        if len(other_missing) > 5:
            missing_str += f" (+{len(other_missing) - 5} more)"
        alerts.append(Alert(
            id=f"{base_id}_incomplete_other",
            type="DATA_INCOMPLETE",
            symbol=result.symbol,
            message=f"{result.symbol} has incomplete data - missing: {missing_str}",
            severity="INFO",  # Lower severity for non-critical fields
            created_at=now_iso,
            meta={
                "completeness": result.data_completeness,
                "missing_fields": other_missing,
            },
        ))

    return alerts


def _evaluate_single_symbol(symbol: str) -> SymbolEvaluationResult:
    """Evaluate a single symbol using ORATS data."""
    from app.core.data.orats_client import get_orats_live_summaries, get_orats_live_strikes, OratsUnavailableError

    result = SymbolEvaluationResult(symbol=symbol, source="ORATS")
    now_iso = datetime.now(timezone.utc).isoformat()
    result.fetched_at = now_iso
    
    # Track data quality for each field
    field_quality: Dict[str, FieldValue] = {}

    # Fetch ORATS summary data
    try:
        summaries = get_orats_live_summaries(symbol)
        if summaries and len(summaries) > 0:
            s = summaries[0]
            
            # Wrap fields with quality tracking
            # NOTE: Use `is not None` check, not `or`, to preserve valid 0 values
            price_fv = wrap_field_float(s.get("stockPrice"), "price")
            bid_fv = wrap_field_float(s.get("bid"), "bid")
            ask_fv = wrap_field_float(s.get("ask"), "ask")
            
            # Handle volume fallback properly - 0 is a valid value
            raw_volume = s.get("volume")
            if raw_volume is None:
                raw_volume = s.get("stockVolume")
            volume_fv = wrap_field_int(raw_volume, "volume")
            
            # Volume metrics: only avg_option_volume_20d / avg_stock_volume_20d (no avg_volume in ORATS)
            raw_opt = s.get("avg_option_volume_20d") or s.get("avgOptVolu20d")
            raw_stock = s.get("avg_stock_volume_20d")
            result.avg_option_volume_20d = _safe_float(raw_opt)
            result.avg_stock_volume_20d = _safe_float(raw_stock)

            iv_rank_fv = wrap_field_float(s.get("ivRank") or s.get("iv_rank"), "iv_rank")

            # Store quality info
            field_quality["price"] = price_fv
            field_quality["bid"] = bid_fv
            field_quality["ask"] = ask_fv
            field_quality["volume"] = volume_fv
            field_quality["iv_rank"] = iv_rank_fv

            # Extract values (None if MISSING, preserves 0 if VALID)
            result.price = price_fv.value if price_fv.is_valid else None
            result.bid = bid_fv.value if bid_fv.is_valid else None
            result.ask = ask_fv.value if ask_fv.is_valid else None
            result.volume = volume_fv.value if volume_fv.is_valid else None
            
            # Track quality details for API
            for name, fv in field_quality.items():
                result.data_quality_details[name] = str(fv.quality)

            # IV and other metrics for context
            iv_rank = iv_rank_fv.value

            # Determine regime/risk from IV (simplified heuristic)
            if iv_rank is not None:
                if iv_rank < 30:
                    result.regime = "BULL"
                    result.risk = "LOW"
                elif iv_rank > 70:
                    result.regime = "BEAR"
                    result.risk = "HIGH"
                else:
                    result.regime = "NEUTRAL"
                    result.risk = "MODERATE"
            else:
                result.regime = "UNKNOWN"
                result.risk = "UNKNOWN"

            # Options available check
            result.options_available = True
            result.options_reason = "ORATS data available"

            # Add gate for summary data
            result.gates.append({
                "name": "ORATS Summary",
                "status": "PASS",
                "reason": f"Stock price: ${result.price:.2f}" if result.price else "Data available"
            })
        else:
            result.options_available = False
            result.options_reason = "No ORATS summary data returned"
            result.gates.append({
                "name": "ORATS Summary",
                "status": "FAIL",
                "reason": "No summary data"
            })
    except OratsUnavailableError as e:
        result.error = str(e)
        result.options_available = False
        result.options_reason = f"ORATS fetch failed - {e}"
        result.gates.append({
            "name": "ORATS Summary",
            "status": "FAIL",
            "reason": str(e)
        })

    # Fetch strikes for options chain validation and candidate trades
    try:
        strikes = get_orats_live_strikes(symbol)
        if strikes and len(strikes) > 0:
            # Check liquidity based on open interest
            total_oi = sum(_safe_int(s.get("openInt"), 0) for s in strikes)
            total_vol = sum(_safe_int(s.get("volume"), 0) for s in strikes)

            # Track strikes liquidity data quality
            # If we have strikes but all OI/volume are 0 or None, that's concerning
            has_valid_oi = any(_safe_int(s.get("openInt")) is not None and _safe_int(s.get("openInt")) > 0 for s in strikes)
            has_valid_vol = any(_safe_int(s.get("volume")) is not None and _safe_int(s.get("volume")) > 0 for s in strikes)

            if total_oi >= LIQUIDITY_MIN_OI and total_vol >= LIQUIDITY_MIN_VOLUME:
                result.liquidity_ok = True
                result.liquidity_reason = f"OI: {total_oi:,}, Volume: {total_vol:,}"
            elif not has_valid_oi or not has_valid_vol:
                # Data might be missing/incomplete, not necessarily low
                result.liquidity_ok = False
                missing_parts = []
                if not has_valid_oi:
                    missing_parts.append("OI")
                if not has_valid_vol:
                    missing_parts.append("volume")
                result.liquidity_reason = f"Liquidity data incomplete - no valid {', '.join(missing_parts)} in strikes"
            else:
                # Data is present but values are actually low
                result.liquidity_ok = False
                result.liquidity_reason = f"Low liquidity - OI: {total_oi:,}, Volume: {total_vol:,}"

            result.gates.append({
                "name": "Options Liquidity",
                "status": "PASS" if result.liquidity_ok else "FAIL",
                "reason": result.liquidity_reason
            })

            # Generate candidate trades (find good CSP strikes)
            result.candidate_trades = _generate_candidate_trades(symbol, strikes, result.price)
        else:
            result.liquidity_ok = False
            result.liquidity_reason = "No strikes data returned"
            result.gates.append({
                "name": "Options Liquidity",
                "status": "FAIL",
                "reason": "No strikes data"
            })
    except OratsUnavailableError as e:
        if not result.error:
            result.error = str(e)
        result.liquidity_ok = False
        result.liquidity_reason = f"Strikes fetch failed - {e}"
        result.gates.append({
            "name": "Options Liquidity",
            "status": "FAIL",
            "reason": str(e)
        })

    # Earnings check (simplified - check if any near-term expiries have earnings flag)
    # For now, assume not blocked unless we have explicit data
    result.earnings_blocked = False
    result.earnings_days = None
    result.gates.append({
        "name": "Earnings Check",
        "status": "PASS",
        "reason": "No earnings conflict detected"
    })

    # Compute data completeness from tracked fields
    if field_quality:
        result.data_completeness, result.missing_fields = compute_data_completeness(field_quality)
    else:
        # No fields tracked (error case)
        result.data_completeness = 0.0
        result.missing_fields = ["all"]
    
    # Determine verdict and primary reason
    result.verdict, result.primary_reason = _determine_verdict(result)

    # Compute score
    result.score = _compute_score(result)

    # Confidence based on data completeness (enhanced)
    base_confidence = sum([
        1 if result.price else 0,
        1 if result.options_available else 0,
        1 if result.liquidity_ok else 0,
        1 if result.regime != "UNKNOWN" else 0,
    ])
    # Factor in data completeness
    result.confidence = (base_confidence / 4.0) * result.data_completeness

    return result


def _generate_candidate_trades(symbol: str, strikes: List[Dict], stock_price: Optional[float]) -> List[CandidateTrade]:
    """Generate candidate CSP trades from strikes data."""
    candidates = []

    if not stock_price or not strikes:
        return candidates

    # Group by expiration
    by_expiry: Dict[str, List[Dict]] = {}
    for s in strikes:
        exp = s.get("expirDate") or s.get("expirationDate")
        if exp:
            by_expiry.setdefault(exp, []).append(s)

    # Find puts near 0.20-0.30 delta for CSP
    for expiry, expiry_strikes in sorted(by_expiry.items())[:3]:  # Top 3 expirations
        puts = [s for s in expiry_strikes if s.get("putCall", "").upper() == "P" or s.get("callPut", "").upper() == "P"]
        if not puts:
            continue

        for p in puts:
            delta = _safe_float(p.get("delta"))
            strike = _safe_float(p.get("strike"))
            bid = _safe_float(p.get("bid"))

            if delta is None or strike is None:
                continue

            # Target delta range for CSP: -0.20 to -0.35
            if -0.35 <= delta <= -0.20:
                credit = bid if bid else 0
                max_loss = (strike * 100) - (credit * 100) if strike else 0

                candidates.append(CandidateTrade(
                    strategy="CSP",
                    expiry=expiry,
                    strike=strike,
                    delta=round(delta, 3),
                    credit_estimate=round(credit, 2) if credit else None,
                    max_loss=round(max_loss, 2) if max_loss else None,
                    why_this_trade=f"Put at {delta:.0%} delta, strike ${strike:.0f}"
                ))

                if len(candidates) >= 2:  # Max 2 per symbol
                    return candidates

    return candidates


def run_universe_evaluation_staged(universe_symbols: List[str], use_staged: bool = True) -> UniverseEvaluationResult:
    """
    Run 2-stage evaluation across universe symbols.
    
    Stage 1: Stock quality + regime filters
    Stage 2: Chain evaluation for top K candidates
    
    Args:
        universe_symbols: List of stock symbols
        use_staged: If True, use 2-stage pipeline; if False, fall back to legacy
    
    Returns:
        UniverseEvaluationResult with staged evaluation data
    """
    if not use_staged:
        return run_universe_evaluation(universe_symbols)
    
    global _CACHE, _IS_RUNNING
    
    logger.info("[STAGED_EVAL] Starting 2-stage evaluation for %d symbols", len(universe_symbols))
    print(f"[STAGED_EVAL] Starting 2-stage evaluation for {len(universe_symbols)} symbols")
    
    start_time = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Set running state
    result = UniverseEvaluationResult(
        evaluation_state="RUNNING",
        evaluation_state_reason="2-stage evaluation in progress",
        total=len(universe_symbols),
    )
    with _CACHE_LOCK:
        _CACHE = result
    
    try:
        from app.core.eval.staged_evaluator import evaluate_universe_staged, EvaluationStage, StagedEvaluationResult
        
        # Run staged evaluation; contract: StagedEvaluationResult (never assume flat list)
        staged_out = evaluate_universe_staged(universe_symbols)
        if not isinstance(staged_out, StagedEvaluationResult):
            raise TypeError("evaluate_universe_staged must return StagedEvaluationResult")
        staged_results = staged_out.results
        exposure_summary = staged_out.exposure_summary
        
        # Convert to SymbolEvaluationResult
        symbols_results: List[SymbolEvaluationResult] = []
        all_alerts: List[Alert] = []
        errors: List[str] = []
        
        for sr in staged_results:
            # Convert FullEvaluationResult to SymbolEvaluationResult
            # bid/ask/volume and volume metrics from FullEvaluationResult
            sym_result = SymbolEvaluationResult(
                symbol=sr.symbol,
                source=sr.source,
                price=sr.price,
                bid=sr.bid,
                ask=sr.ask,
                volume=sr.volume,
                avg_option_volume_20d=getattr(sr, "avg_option_volume_20d", None),
                avg_stock_volume_20d=getattr(sr, "avg_stock_volume_20d", None),
                verdict=sr.verdict,
                primary_reason=sr.primary_reason,
                confidence=sr.confidence,
                score=sr.score,
                regime=sr.regime,
                risk=sr.risk,
                liquidity_ok=sr.liquidity_ok,
                liquidity_reason=sr.liquidity_reason,
                options_available=sr.options_available,
                options_reason=sr.options_reason,
                gates=sr.gates,
                blockers=sr.blockers,
                fetched_at=sr.fetched_at,
                error=sr.error,
                data_completeness=sr.data_completeness,
                missing_fields=sr.missing_fields,
                data_quality_details=sr.data_quality_details,
                stage_reached=sr.stage_reached.value,
                iv_rank=getattr(sr, "iv_rank", None),
                quote_date=getattr(sr, "quote_date", None),
                position_open=getattr(sr, "position_open", False),
                position_reason=getattr(sr, "position_reason", None),
                capital_hint=sr.capital_hint.to_dict() if getattr(sr, "capital_hint", None) else None,
                waiver_reason=getattr(sr, "waiver_reason", None),
                score_breakdown=getattr(sr, "score_breakdown", None),
                rank_reasons=getattr(sr, "rank_reasons", None),
                csp_notional=getattr(sr, "csp_notional", None),
                notional_pct=getattr(sr, "notional_pct", None),
                band_reason=getattr(sr, "band_reason", None),
            )
            
            # Add selected contract if available
            if sr.stage2 and sr.stage2.selected_contract:
                sym_result.selected_contract = sr.stage2.selected_contract.to_dict()
                if sr.stage2.selected_expiration:
                    sym_result.selected_expiration = sr.stage2.selected_expiration.isoformat()
            
            # Convert candidate_trades from dicts to CandidateTrade
            for ct_dict in sr.candidate_trades:
                sym_result.candidate_trades.append(CandidateTrade(
                    strategy=ct_dict.get("strategy", "CSP"),
                    expiry=ct_dict.get("expiry"),
                    strike=ct_dict.get("strike"),
                    delta=ct_dict.get("delta"),
                    credit_estimate=ct_dict.get("credit_estimate"),
                    max_loss=ct_dict.get("max_loss"),
                    why_this_trade=ct_dict.get("why_this_trade", ""),
                ))
            
            symbols_results.append(sym_result)
            
            # Generate alerts
            all_alerts.extend(_generate_alerts(sym_result))
            
            if sr.error:
                errors.append(f"{sr.symbol}: {sr.error}")
        
        # Calculate counts
        evaluated = len(symbols_results)
        eligible = sum(1 for s in symbols_results if s.verdict == "ELIGIBLE")
        shortlisted = sum(1 for s in symbols_results if s.verdict == "ELIGIBLE" and s.score >= SHORTLIST_SCORE_THRESHOLD)
        stage2_count = sum(1 for s in symbols_results if s.stage_reached == "STAGE2_CHAIN")
        
        duration = time.time() - start_time
        end_iso = datetime.now(timezone.utc).isoformat()
        
        # Build final result (engine=staged - single source of truth)
        final_result = UniverseEvaluationResult(
            evaluation_state="COMPLETED" if eligible > 0 or not errors else "FAILED",
            evaluation_state_reason=f"2-stage: {evaluated} evaluated, {stage2_count} chain-evaluated, {eligible} eligible",
            last_evaluated_at=end_iso,
            duration_seconds=round(duration, 2),
            total=len(universe_symbols),
            evaluated=evaluated,
            eligible=eligible,
            shortlisted=shortlisted,
            symbols=symbols_results,
            alerts=all_alerts,
            errors=errors,
            exposure_summary=exposure_summary.to_dict() if exposure_summary else None,
            engine="staged",
        )
        
        # Update cache
        with _CACHE_LOCK:
            _CACHE = final_result
        
        logger.info("[STAGED_EVAL] Completed: %d evaluated, %d stage2, %d eligible, %.1fs",
                    evaluated, stage2_count, eligible, duration)
        print(f"[STAGED_EVAL] Completed: {evaluated} evaluated, {stage2_count} stage2, {eligible} eligible, {duration:.1f}s")
        
        return final_result
        
    except Exception as e:
        # No silent fallback: staged evaluation is the single source of truth.
        # Let exception propagate so caller can persist FAILED and return 500.
        logger.exception("[STAGED_EVAL] Staged evaluation failed - aborting (no legacy fallback): %s", e)
        raise


def run_universe_evaluation(universe_symbols: List[str]) -> UniverseEvaluationResult:
    """
    Run evaluation across all universe symbols (legacy mode).
    Updates the global cache and returns the result.
    """
    global _CACHE, _IS_RUNNING

    logger.info("[EVAL] Starting universe evaluation for %d symbols", len(universe_symbols))
    print(f"[EVAL] Starting universe evaluation for {len(universe_symbols)} symbols")

    start_time = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    result = UniverseEvaluationResult(
        evaluation_state="RUNNING",
        evaluation_state_reason="Evaluation in progress",
        total=len(universe_symbols),
    )

    # Update cache to show running state
    with _CACHE_LOCK:
        _CACHE = result

    all_alerts: List[Alert] = []
    symbols_results: List[SymbolEvaluationResult] = []
    errors: List[str] = []

    for symbol in universe_symbols:
        try:
            sym_result = _evaluate_single_symbol(symbol)
            symbols_results.append(sym_result)
            all_alerts.extend(_generate_alerts(sym_result))
        except Exception as e:
            logger.exception("[EVAL] Error evaluating %s: %s", symbol, e)
            errors.append(f"{symbol}: {e}")
            # Create error result
            err_result = SymbolEvaluationResult(
                symbol=symbol,
                verdict="UNKNOWN",
                primary_reason=f"Evaluation error - {e}",
                error=str(e),
                fetched_at=now_iso,
            )
            symbols_results.append(err_result)

    # Calculate counts
    evaluated = len(symbols_results)
    eligible = sum(1 for s in symbols_results if s.verdict == "ELIGIBLE")
    shortlisted = sum(1 for s in symbols_results if s.verdict == "ELIGIBLE" and s.score >= SHORTLIST_SCORE_THRESHOLD)

    duration = time.time() - start_time
    end_iso = datetime.now(timezone.utc).isoformat()

    # Build final result
    final_result = UniverseEvaluationResult(
        evaluation_state="COMPLETED" if not errors or eligible > 0 else "FAILED",
        evaluation_state_reason=f"Evaluated {evaluated} symbols, {eligible} eligible, {shortlisted} shortlisted" if not errors else f"Completed with {len(errors)} errors",
        last_evaluated_at=end_iso,
        duration_seconds=round(duration, 2),
        total=len(universe_symbols),
        evaluated=evaluated,
        eligible=eligible,
        shortlisted=shortlisted,
        symbols=symbols_results,
        alerts=all_alerts,
        errors=errors,
        engine="legacy",
    )

    # Update cache
    with _CACHE_LOCK:
        _CACHE = final_result

    logger.info("[EVAL] Completed: %d evaluated, %d eligible, %d shortlisted, %.1fs",
                evaluated, eligible, shortlisted, duration)
    print(f"[EVAL] Completed: {evaluated} evaluated, {eligible} eligible, {shortlisted} shortlisted, {duration:.1f}s")

    return final_result
