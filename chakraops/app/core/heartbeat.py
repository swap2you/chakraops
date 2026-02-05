# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Background evaluation heartbeat for ChakraOps (Production - Hardened).

This module provides a background evaluation loop that:
- Re-evaluates CSP candidates every N seconds (configurable)
- Updates Daily Trading Plan
- Emits alerts only on state changes (no duplicates)
- Uses cached market data when fresh (<5 minutes)
- Runs safely in background without blocking Streamlit UI
- Prevents duplicate threads (process-level singleton)
- Never calls Streamlit APIs in background thread
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger(__name__)

# Import persistence early to trigger schema initialization
from app.core.persistence import initialize_schema  # noqa: F401

# ET timezone (US/Eastern)
_ET_TZ = pytz.timezone("America/New_York") if pytz else None


def ensure_et_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is ET timezone-aware (normalize to ET).
    
    Converts naive or UTC datetimes to ET timezone-aware.
    If pytz is not available, converts to UTC-aware.
    
    Parameters
    ----------
    dt:
        Datetime to normalize (can be naive, UTC-aware, or ET-aware).
    
    Returns
    -------
    Optional[datetime]
        ET timezone-aware datetime, or None if input is None.
    """
    if dt is None:
        return None
    
    if _ET_TZ is None:
        # Fallback: ensure UTC-aware if pytz not available
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    
    # If naive, assume UTC and convert to ET
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to ET
    return dt.astimezone(_ET_TZ)

# Configuration constants
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("CHAKRAOPS_HEARTBEAT_SECONDS", "60"))
MARKET_DATA_STALE_THRESHOLD_MINUTES = 5
REGIME_STALE_THRESHOLD_MINUTES = 5
DATA_STALE_HALT_THRESHOLD_MINUTES = 15
CANDIDATE_REMOVAL_ALERT_COOLDOWN_HOURS = 6

# CSP Scoring Configuration (Phase 2B Step 2)
# Imported from app.core.config.trade_rules
from app.core.config.trade_rules import MIN_PRICE, MAX_PRICE, TARGET_LOW, TARGET_HIGH

# Process-level singleton (module global)
_process_instance: Optional[HeartbeatManager] = None
_process_lock = threading.Lock()


class HeartbeatManager:
    """Manages background evaluation heartbeat.
    
    Thread-safe singleton that runs evaluation cycles in background.
    Uses process-level singleton to prevent duplicate threads across Streamlit reruns.
    """
    
    def __init__(self):
        # Log DB path at heartbeat startup (DB Path Unification Fix)
        from app.core.config.paths import DB_PATH
        logger.info(f"[HEARTBEAT] DB_PATH={DB_PATH.absolute()}")
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._start_lock = threading.Lock()
        
        # Market data cache with timestamps
        self._market_data_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()
        
        # Previous state tracking for change detection
        self._previous_candidate_symbols: Set[str] = set()
        self._previous_regime: Optional[str] = None
        self._last_removal_alert_time: Optional[datetime] = None
        
        # Health tracking
        self._last_cycle_time: Optional[datetime] = None
        self._last_cycle_status: str = "UNKNOWN"
        self._last_data_timestamp: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._health_lock = threading.Lock()
        
        # Cycle evaluation details (for debug panel)
        self._last_cycle_eval: Dict[str, Any] = {
            "symbols_evaluated": 0,
            "csp_candidates_count": 0,
            "rejected_symbols_count": 0,
            "rejection_reasons": {},
            "market_data_age_minutes": 0.0,
            "enabled_universe_size": 0,
        }
    
    @classmethod
    def get_instance(cls) -> HeartbeatManager:
        """Get process-level singleton instance (thread-safe)."""
        global _process_instance, _process_lock
        
        if _process_instance is None:
            with _process_lock:
                if _process_instance is None:
                    _process_instance = cls()
        return _process_instance
    
    def start(self) -> None:
        """Start heartbeat thread (idempotent, checks if thread is alive).
        
        This method is safe to call multiple times - it will not spawn
        duplicate threads even across Streamlit reruns.
        """
        with self._start_lock:
            # Check if thread is already alive (process-level check)
            if self._thread is not None and self._thread.is_alive():
                logger.debug("[HEARTBEAT] Thread already alive, skipping start")
                return
            
            # Check running flag as secondary guard
            if self._running:
                logger.debug("[HEARTBEAT] Already marked as running, skipping start")
                return
            
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="ChakraOps-Heartbeat"
            )
            self._thread.start()
            self._running = True
            logger.info(f"[HEARTBEAT] Started background evaluation heartbeat (interval={HEARTBEAT_INTERVAL_SECONDS}s)")
    
    def stop(self) -> None:
        """Stop heartbeat thread (idempotent)."""
        with self._start_lock:
            if not self._running:
                return
            
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5.0)
            self._running = False
            logger.info("[HEARTBEAT] Stopped background evaluation heartbeat")
    
    def is_running(self) -> bool:
        """Check if heartbeat is running (checks thread is alive)."""
        return self._running and self._thread is not None and self._thread.is_alive()
    
    def get_health(self) -> Dict[str, Any]:
        """Get heartbeat health status (thread-safe, no Streamlit calls).
        
        Returns
        -------
        Dict[str, Any]
            Health status with last_cycle_time, status, data_timestamp, last_error.
        """
        with self._health_lock:
            return {
                "last_cycle_time": self._last_cycle_time.isoformat() if self._last_cycle_time else None,
                "status": self._last_cycle_status,
                "data_timestamp": self._last_data_timestamp.isoformat() if self._last_data_timestamp else None,
                "last_error": self._last_error,
                "is_running": self.is_running(),
            }
    
    def get_cycle_eval_details(self) -> Dict[str, Any]:
        """Get last cycle evaluation details (thread-safe, no Streamlit calls).
        
        Returns
        -------
        Dict[str, Any]
            Cycle evaluation details with symbols evaluated, candidates, rejections, etc.
        """
        with self._health_lock:
            return self._last_cycle_eval.copy()
    
    def _update_health(
        self,
        status: str,
        data_timestamp: Optional[datetime] = None,
        error: Optional[str] = None
    ) -> None:
        """Update health status (thread-safe, no Streamlit calls)."""
        with self._health_lock:
            # Use ET timezone for consistency
            if _ET_TZ:
                self._last_cycle_time = datetime.now(_ET_TZ)
            else:
                self._last_cycle_time = datetime.now(timezone.utc)
            self._last_cycle_status = status
            if data_timestamp:
                self._last_data_timestamp = ensure_et_aware(data_timestamp)
            if error:
                self._last_error = error
            elif error is None:
                # Clear error on successful cycle
                self._last_error = None
    
    def _run_loop(self) -> None:
        """Main heartbeat loop (runs in background thread - NO Streamlit calls)."""
        logger.info("[HEARTBEAT] Background evaluation loop started")
        
        while not self._stop_event.is_set():
            try:
                cycle_start = time.time()
                logger.info("[HEARTBEAT] cycle start")
                
                # Run evaluation cycle
                candidates_count, alerts_count = self._evaluate_cycle()
                
                logger.info(
                    f"[HEARTBEAT] candidates={candidates_count} alerts={alerts_count}"
                )
                
                # Update health
                self._update_health("SUCCESS")
                
                # Calculate sleep time (ensure we sleep for full interval)
                cycle_duration = time.time() - cycle_start
                sleep_time = max(0, HEARTBEAT_INTERVAL_SECONDS - cycle_duration)
                
                # Sleep with periodic checks for stop event
                if sleep_time > 0:
                    self._stop_event.wait(timeout=sleep_time)
            
            except Exception as e:
                error_msg = str(e)
                logger.error(f"[HEARTBEAT] Error in evaluation cycle: {e}", exc_info=True)
                self._update_health("ERROR", error=error_msg)
                # Continue loop even on error (don't crash)
                self._stop_event.wait(timeout=HEARTBEAT_INTERVAL_SECONDS)
        
        logger.info("[HEARTBEAT] Background evaluation loop stopped")
    
    def run_one_cycle(self) -> tuple[int, int]:
        """Run one evaluation cycle (for UI-triggered refresh after snapshot build)."""
        return self._evaluate_cycle()
    
    def _evaluate_cycle(self) -> tuple[int, int]:
        """Run one evaluation cycle (NO Streamlit calls).
        
        Returns
        -------
        tuple[int, int]
            (candidates_count, alerts_count)
        """
        try:
            symbols_evaluated = 0
            # Step 1: Get or compute regime (check freshness)
            regime_result, regime_age_minutes = self._get_regime_with_age()
            if not regime_result:
                # Step 3: If no regime exists, try to compute it (bootstrap)
                logger.info("[HEARTBEAT] No regime data available, attempting to compute regime...")
                regime_result = self._recompute_regime()
                if not regime_result:
                    logger.warning("[HEARTBEAT] Failed to compute regime, skipping cycle")
                    self._update_health("NO_REGIME")
                    # Update eval details with partial info
                    with self._health_lock:
                        self._last_cycle_eval = {
                            "symbols_evaluated": 0,
                            "csp_candidates_count": 0,
                            "rejected_symbols_count": 0,
                            "rejection_reasons": {"No regime data": 1},
                            "market_data_age_minutes": 0.0,
                            "enabled_universe_size": 0,
                        }
                    return 0, 0
                # Re-fetch regime after computation
                regime_result, regime_age_minutes = self._get_regime_with_age()
                if not regime_result:
                    logger.warning("[HEARTBEAT] Regime computed but not found in DB, skipping cycle")
                    return 0, 0
            
            # Check if regime is stale
            if regime_age_minutes > REGIME_STALE_THRESHOLD_MINUTES:
                logger.warning(f"[HEARTBEAT] Regime is stale ({regime_age_minutes:.1f} min old)")
                # Recompute regime if stale
                regime_result = self._recompute_regime()
                if not regime_result:
                    logger.error("[HEARTBEAT] Failed to recompute regime")
                    self._update_health("REGIME_STALE")
                    # Update eval details with partial info
                    with self._health_lock:
                        self._last_cycle_eval = {
                            "symbols_evaluated": 0,
                            "csp_candidates_count": 0,
                            "rejected_symbols_count": 0,
                            "rejection_reasons": {"Regime recomputation failed": 1},
                            "market_data_age_minutes": 0.0,
                            "enabled_universe_size": 0,
                        }
                    return 0, 0
            
            regime = regime_result.get("regime")
            if regime != "RISK_ON":
                # No candidates in RISK_OFF regime - still track what we know
                from app.core.persistence import get_enabled_symbols
                symbols = get_enabled_symbols()
                with self._health_lock:
                    self._last_cycle_eval = {
                        "symbols_evaluated": len(symbols) if symbols else 0,
                        "csp_candidates_count": 0,
                        "rejected_symbols_count": len(symbols) if symbols else 0,
                        "rejection_reasons": {f"Regime is {regime} (not RISK_ON)": len(symbols) if symbols else 1},
                        "market_data_age_minutes": 0.0,
                        "enabled_universe_size": len(symbols) if symbols else 0,
                    }
                return 0, 0
            
            # Step 2: Load latest active snapshot and enabled symbols (Phase 2B)
            from app.core.persistence import get_enabled_symbols
            from app.core.market_snapshot import get_active_snapshot, load_snapshot_data, normalize_symbol
            
            # Diagnostic logging (Heartbeat Diagnostic Verification)
            logger.info("[HEARTBEAT][DIAG] Starting symbol loading diagnostics")
            
            enabled_symbols = get_enabled_symbols()
            # DEV: if universe is empty, use default_universe.txt for this cycle only (no DB overwrite)
            if not enabled_symbols and os.getenv("CHAKRAOPS_DEV", "").lower() in ("1", "true", "yes"):
                try:
                    from app.core.dev_seed import load_default_universe
                    enabled_symbols = load_default_universe()
                    logger.info("[HEARTBEAT] DEV: enabled universe empty, using default_universe.txt (%d symbols)", len(enabled_symbols))
                except Exception as e:
                    logger.warning("[HEARTBEAT] DEV: failed to load default_universe: %s", e)
            enabled_universe_size = len(enabled_symbols) if enabled_symbols else 0
            
            logger.info(f"[HEARTBEAT][DIAG] enabled_symbols length={enabled_universe_size}")
            if enabled_symbols:
                logger.info(f"[HEARTBEAT][DIAG] enabled_symbols sample={enabled_symbols[:10]}")
            else:
                logger.warning("[HEARTBEAT][DIAG] enabled_symbols is empty or None")
            
            if enabled_universe_size == 0:
                logger.warning("[HEARTBEAT] No enabled symbols, skipping cycle")
                logger.warning("[HEARTBEAT][DIAG] GUARD: enabled_symbols is empty - skipping evaluation")
                with self._health_lock:
                    self._last_cycle_eval = {
                        "symbols_evaluated": 0,
                        "csp_candidates_count": 0,
                        "rejected_symbols_count": 0,
                        "rejection_reasons": {"No enabled symbols": 1},
                        "market_data_age_minutes": 0.0,
                        "enabled_universe_size": 0,
                    }
                return 0, 0
            
            # Load latest active snapshot
            snapshot = get_active_snapshot()
            if not snapshot:
                # Log once per session if snapshot missing
                if not hasattr(self, '_snapshot_missing_logged'):
                    logger.warning("[HEARTBEAT] No active snapshot available, skipping cycle")
                    self._snapshot_missing_logged = True
                self._update_health("NO_SNAPSHOT")
                with self._health_lock:
                    self._last_cycle_eval = {
                        "symbols_evaluated": 0,
                        "csp_candidates_count": 0,
                        "rejected_symbols_count": enabled_universe_size,
                        "rejection_reasons": {"No snapshot available": enabled_universe_size},
                        "market_data_age_minutes": 0.0,
                        "enabled_universe_size": enabled_universe_size,
                    }
                return 0, 0
            
            # Step 3: Compute intersection: enabled symbols ∩ snapshot symbols
            snapshot_id = snapshot["snapshot_id"]
            logger.info(f"[HEARTBEAT] Evaluating cycle: snapshot_id={snapshot_id}")
            snapshot_data = load_snapshot_data(snapshot_id)
            snapshot_symbols = set(snapshot_data.keys())  # Already normalized
            
            # Diagnostic logging (Heartbeat Diagnostic Verification)
            logger.info(f"[HEARTBEAT][DIAG] snapshot_symbols length={len(snapshot_symbols)}")
            if snapshot_symbols:
                logger.info(f"[HEARTBEAT][DIAG] snapshot_symbols sample={sorted(list(snapshot_symbols))[:10]}")
            
            # Normalize enabled symbols for intersection
            enabled_symbols_normalized = {normalize_symbol(s) for s in enabled_symbols}
            symbols_to_eval = enabled_symbols_normalized & snapshot_symbols
            rejected_symbols = enabled_symbols_normalized - snapshot_symbols
            
            # Diagnostic logging
            logger.info(f"[HEARTBEAT][DIAG] enabled_symbols_normalized length={len(enabled_symbols_normalized)}")
            logger.info(f"[HEARTBEAT][DIAG] intersection length={len(symbols_to_eval)}")
            if enabled_symbols_normalized:
                logger.info(f"[HEARTBEAT][DIAG] enabled_symbols_normalized sample={sorted(list(enabled_symbols_normalized))[:10]}")
            if symbols_to_eval:
                logger.info(f"[HEARTBEAT][DIAG] intersection sample={sorted(list(symbols_to_eval))[:10]}")
            if rejected_symbols:
                logger.info(f"[HEARTBEAT][DIAG] rejected_symbols sample={sorted(list(rejected_symbols))[:10]}")
            
            # Log counts and first 5 symbols
            logger.info(f"[HEARTBEAT] Enabled universe: {enabled_universe_size} symbols")
            logger.info(f"[HEARTBEAT] Snapshot symbols: {len(snapshot_symbols)} symbols")
            logger.info(f"[HEARTBEAT] Intersection (to evaluate): {len(symbols_to_eval)} symbols")
            logger.info(f"[HEARTBEAT] Rejected (missing from snapshot): {len(rejected_symbols)} symbols")
            if enabled_symbols_normalized:
                logger.info(f"[HEARTBEAT] First 5 enabled: {sorted(list(enabled_symbols_normalized))[:5]}")
            if snapshot_symbols:
                logger.info(f"[HEARTBEAT] First 5 snapshot: {sorted(list(snapshot_symbols))[:5]}")
            if symbols_to_eval:
                logger.info(f"[HEARTBEAT] First 5 intersection: {sorted(list(symbols_to_eval))[:5]}")
            
            if not symbols_to_eval:
                logger.warning("[HEARTBEAT] No symbols to evaluate (empty intersection)")
                with self._health_lock:
                    self._last_cycle_eval = {
                        "symbols_evaluated": 0,
                        "csp_candidates_count": 0,
                        "rejected_symbols_count": len(rejected_symbols),
                        "rejection_reasons": {"Symbol missing from snapshot": len(rejected_symbols)},
                        "market_data_age_minutes": snapshot.get("data_age_minutes", 0.0),
                        "enabled_universe_size": enabled_universe_size,
                    }
                return 0, 0
            
            # Get snapshot timestamp for data age
            snapshot_timestamp_et = snapshot.get("snapshot_timestamp_et")
            data_timestamp = None
            data_stale_minutes = snapshot.get("data_age_minutes", 0.0)
            if snapshot_timestamp_et:
                try:
                    data_timestamp = datetime.fromisoformat(snapshot_timestamp_et)
                    data_timestamp = ensure_et_aware(data_timestamp)
                except Exception:
                    pass
            
            # Step 4: Evaluate each symbol using deterministic CSP scoring (Phase 2B Step 2/3)
            from app.core.market_snapshot import get_snapshot_prices
            from app.core.persistence import upsert_csp_evaluations, list_universe_symbols
            
            # Get price/volume/iv_rank data from snapshot (Phase 2B Step 3)
            snapshot_data_map = get_snapshot_prices(snapshot_id)
            
            # Get universe metadata (for priority/tier if available)
            universe_rows = list_universe_symbols()
            universe_metadata_map: Dict[str, Dict[str, Any]] = {}
            for row in universe_rows:
                symbol_norm = normalize_symbol(row["symbol"])
                universe_metadata_map[symbol_norm] = {
                    "enabled": bool(row.get("enabled")),
                    "notes": row.get("notes"),
                }
            
            # Evaluate each symbol
            evaluations: List[Dict[str, Any]] = []
            eligible_count = 0
            rejected_count = 0
            low_liquidity_count = 0
            iv_too_low_count = 0
            
            for symbol in symbols_to_eval:
                symbol_data = snapshot_data_map.get(symbol, {})
                price = symbol_data.get("price")
                volume = symbol_data.get("volume")
                iv_rank = symbol_data.get("iv_rank")
                universe_metadata = universe_metadata_map.get(symbol)
                
                eval_result = self.evaluate_csp_symbol(
                    symbol=symbol,
                    price=price,
                    volume=volume,
                    iv_rank=iv_rank,
                    regime=regime,
                    snapshot_age_minutes=data_stale_minutes,
                    universe_metadata=universe_metadata,
                )
                
                # Track rejection reason counts
                if not eval_result["eligible"]:
                    if "low_liquidity" in eval_result["rejection_reasons"]:
                        low_liquidity_count += 1
                    if "iv_too_low" in eval_result["rejection_reasons"]:
                        iv_too_low_count += 1
                
                evaluations.append(eval_result)
                symbols_evaluated += 1
                
                if eval_result["eligible"]:
                    eligible_count += 1
                else:
                    rejected_count += 1
            
            # Phase 5: Options-layer contract selection for stock-eligible symbols
            _chain_provider = None
            try:
                from app.data.options_chain_provider import OratsOptionsChainProvider
                _chain_provider = OratsOptionsChainProvider()
            except Exception as _e:
                logger.debug("[HEARTBEAT] Options chain provider unavailable, skipping contract selection: %s", _e)
            if _chain_provider is not None:
                from app.core.options.contract_selector import select_csp_contract
                for eval_result in evaluations:
                    if not eval_result.get("eligible"):
                        continue
                    ctx = {
                        "price": eval_result.get("features", {}).get("price"),
                        "iv_rank": eval_result.get("features", {}).get("iv_rank"),
                        "regime": eval_result.get("regime_context", {}).get("regime"),
                        "snapshot_age_minutes": eval_result.get("features", {}).get("snapshot_age_minutes"),
                    }
                    r = select_csp_contract(eval_result["symbol"], ctx, _chain_provider, None)
                    if not r.eligible:
                        eval_result["eligible"] = False
                        eval_result["rejection_reasons"] = list(eval_result.get("rejection_reasons", [])) + r.rejection_reasons
                        (eval_result.setdefault("features", {})).update({
                            "options_rejection_reasons": r.rejection_reasons,
                            "options_debug_inputs": r.debug_inputs,
                        })
                        eligible_count -= 1
                        rejected_count += 1
                    else:
                        (eval_result.setdefault("features", {})).update({
                            "chosen_contract": r.chosen_contract,
                            "options_roc": r.roc,
                            "options_spread_pct": r.spread_pct,
                            "options_dte": r.dte,
                        })
            
            # Step 3: Persist evaluations to database and log insertion
            upsert_csp_evaluations(snapshot_id, evaluations)
            logger.info(
                f"[HEARTBEAT] wrote csp_evaluations snapshot_id={snapshot_id} "
                f"total={len(evaluations)} eligible={eligible_count} rejected={rejected_count}"
            )
            
            # Compute top rejection reasons
            rejection_reason_counts: Dict[str, int] = {}
            for eval_result in evaluations:
                if not eval_result["eligible"]:
                    for reason in eval_result["rejection_reasons"]:
                        rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1
            
            # Log evaluation summary (Phase 2B Step 3)
            logger.info(
                f"[HEARTBEAT] Evaluation summary: snapshot_id={snapshot_id[:8]}..., "
                f"enabled={enabled_universe_size}, snapshot={len(snapshot_symbols)}, "
                f"intersection={len(symbols_to_eval)}, eligible={eligible_count}, "
                f"rejected={rejected_count}"
            )
            logger.info(
                f"[HEARTBEAT] Rejection breakdown: low_liquidity={low_liquidity_count}, "
                f"iv_too_low={iv_too_low_count}"
            )
            
            if rejection_reason_counts:
                top_reasons = sorted(rejection_reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                logger.info(f"[HEARTBEAT] Top 3 rejection reasons: {top_reasons}")
            
            # Step 5: Legacy CSP candidate finding (for backward compatibility)
            # Filter snapshot data to only symbols we can evaluate
            symbol_to_df = {s: snapshot_data[s] for s in symbols_to_eval if s in snapshot_data}
            
            from app.core.wheel import find_csp_candidates
            candidates = find_csp_candidates(symbol_to_df, regime)
            
            # Step 5: Score assignment-worthiness
            from app.core.assignment_scoring import score_assignment_worthiness
            from app.core.persistence import (
                save_assignment_profile,
                is_assignment_blocked,
                create_alert,
            )
            from app.db.database import log_csp_candidates
            
            actionable_candidates = []
            blocked_count = 0
            rejection_reasons: Dict[str, int] = {}
            
            # Track symbols that produced candidates vs those that didn't
            symbols_with_candidates = set()
            
            for candidate in candidates:
                symbols_with_candidates.add(candidate.get("symbol", ""))
                try:
                    # Score assignment-worthiness
                    assignment_result = score_assignment_worthiness(
                        candidate,
                        regime
                    )
                    
                    # Add assignment data
                    candidate["assignment_score"] = assignment_result["assignment_score"]
                    candidate["assignment_label"] = assignment_result["assignment_label"]
                    candidate["assignment_reasons"] = assignment_result["assignment_reasons"]
                    
                    # Save assignment profile
                    save_assignment_profile(
                        symbol=candidate["symbol"],
                        assignment_score=assignment_result["assignment_score"],
                        assignment_label=assignment_result["assignment_label"],
                        operator_override=False,
                        override_reason=None,
                    )
                    
                    # Check if blocked
                    if is_assignment_blocked(candidate["symbol"]):
                        blocked_count += 1
                        candidate["blocked"] = True
                        reason = "Assignment blocked (RENT_ONLY)"
                        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    else:
                        candidate["blocked"] = False
                        actionable_candidates.append(candidate)
                
                except RuntimeError as e:
                    # Assignment scoring failed - emit HALT alert
                    error_msg = f"Assignment scoring failed for {candidate.get('symbol', 'UNKNOWN')}: {e}"
                    logger.error(f"[HEARTBEAT] {error_msg}")
                    create_alert(
                        f"Assignment scoring failed for {candidate.get('symbol', 'UNKNOWN')}. CSP blocked.",
                        level="HALT"
                    )
                    candidate["blocked"] = True
                    blocked_count += 1
                    reason = "Assignment scoring failed"
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            
            # Track symbols that didn't produce any candidates
            symbols_without_candidates = max(0, symbols_evaluated - len(symbols_with_candidates))
            if symbols_without_candidates > 0:
                reason = "No CSP candidates found"
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + symbols_without_candidates
            
            # Step 7: Update daily tracking (ET date)
            self._update_daily_tracking(actionable_candidates)
            
            # Step 8: Detect state changes and emit alerts
            alerts_count = self._detect_state_changes(actionable_candidates, regime)
            
            # Step 9: Update previous state
            self._previous_candidate_symbols = {
                c["symbol"] for c in actionable_candidates
            }
            self._previous_regime = regime
            
            # Step 10: Update cycle evaluation details (Phase 2B Step 2)
            with self._health_lock:
                self._last_cycle_eval = {
                    "symbols_evaluated": len(symbols_to_eval),
                    "csp_candidates_count": eligible_count,  # Use new evaluation count
                    "rejected_symbols_count": len(rejected_symbols) + rejected_count,
                    "rejection_reasons": rejection_reason_counts,  # Use new rejection reasons
                    "market_data_age_minutes": data_stale_minutes,
                    "enabled_universe_size": enabled_universe_size,
                }
            
            # Update health with data timestamp
            self._update_health("SUCCESS", data_timestamp=data_timestamp)
            
            return len(actionable_candidates), alerts_count
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[HEARTBEAT] Error in evaluation cycle: {e}", exc_info=True)
            self._update_health("ERROR", error=error_msg)
            return 0, 0
    
    def _get_regime_with_age(self) -> tuple[Optional[Dict[str, Any]], float]:
        """Get regime snapshot with age in minutes (from market_regimes table, Phase 2B).
        
        Returns
        -------
        tuple[Optional[Dict[str, Any]], float]
            (Regime result dict, age in minutes) or (None, 0.0) if not available.
        """
        try:
            from app.core.persistence import get_latest_regime
            from app.core.engine.regime_gate import evaluate_regime_gate
            
            regime_data = get_latest_regime()
            if not regime_data:
                return None, 0.0
            
            # Convert market_regimes format to expected format
            regime = regime_data["regime"]
            computed_at_str = regime_data.get("computed_at")
            
            # Apply volatility kill switch (Phase 2.2): may override to RISK_OFF with reason
            regime_mapped, regime_reason = evaluate_regime_gate(regime)
            
            if computed_at_str is None:
                logger.warning("[HEARTBEAT] Regime computed_at is None, cannot compute age")
                out = {
                    "regime": regime_mapped,
                    "confidence": 100 if regime != "UNKNOWN" else 0,
                    "details": {
                        "original_regime": regime,
                        "benchmark_symbol": regime_data.get("benchmark_symbol"),
                        "benchmark_return": regime_data.get("benchmark_return"),
                    },
                    "created_at": computed_at_str,
                }
                if regime_reason:
                    out["regime_reason"] = regime_reason
                return out, 0.0
            
            # Parse and normalize to ET
            try:
                computed_at = datetime.fromisoformat(computed_at_str)
                computed_at_et = ensure_et_aware(computed_at)
                
                # Get current time in ET
                if _ET_TZ:
                    now_et = datetime.now(_ET_TZ)
                else:
                    now_et = ensure_et_aware(datetime.now(timezone.utc))
                
                if computed_at_et is None or now_et is None:
                    logger.warning("[HEARTBEAT] Failed to normalize timestamps for regime age calculation")
                    out = {
                        "regime": regime_mapped,
                        "confidence": 100 if regime != "UNKNOWN" else 0,
                        "details": {
                            "original_regime": regime,
                            "benchmark_symbol": regime_data.get("benchmark_symbol"),
                            "benchmark_return": regime_data.get("benchmark_return"),
                        },
                        "created_at": computed_at_str,
                    }
                    if regime_reason:
                        out["regime_reason"] = regime_reason
                    return out, 0.0
                
                age_minutes = (now_et - computed_at_et).total_seconds() / 60.0
            except (ValueError, TypeError) as e:
                logger.warning(f"[HEARTBEAT] Failed to parse regime computed_at '{computed_at_str}': {e}")
                out = {
                    "regime": regime_mapped,
                    "confidence": 100 if regime != "UNKNOWN" else 0,
                    "details": {
                        "original_regime": regime,
                        "benchmark_symbol": regime_data.get("benchmark_symbol"),
                        "benchmark_return": regime_data.get("benchmark_return"),
                    },
                    "created_at": computed_at_str,
                }
                if regime_reason:
                    out["regime_reason"] = regime_reason
                return out, 0.0
            
            out = {
                "regime": regime_mapped,
                "confidence": 100 if regime != "UNKNOWN" else 0,
                "details": {
                    "original_regime": regime,
                    "benchmark_symbol": regime_data.get("benchmark_symbol"),
                    "benchmark_return": regime_data.get("benchmark_return"),
                },
                "created_at": computed_at_str,
            }
            if regime_reason:
                out["regime_reason"] = regime_reason
            return out, age_minutes
        except Exception as e:
            logger.error(f"[HEARTBEAT] Failed to get regime: {e}")
            return None, 0.0
    
    def evaluate_csp_symbol(
        self,
        symbol: str,
        price: Optional[float],
        volume: Optional[float],
        iv_rank: Optional[float],
        regime: str,
        snapshot_age_minutes: float,
        universe_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Evaluate a single symbol for CSP eligibility and score (Phase 2B Step 2/3).
        
        Deterministic scoring using only snapshot data and regime.
        No live providers, no options chain assumptions.
        
        Parameters
        ----------
        symbol:
            Symbol to evaluate (normalized).
        price:
            Latest price from snapshot.
        volume:
            Latest volume from snapshot (optional).
        iv_rank:
            Latest IV rank from snapshot (optional, 0-100).
        regime:
            Market regime: "RISK_ON", "RISK_OFF", or "UNKNOWN".
        snapshot_age_minutes:
            Age of snapshot data in minutes.
        universe_metadata:
            Optional metadata from symbol_universe (for priority/tier).
        
        Returns
        -------
        Dict[str, Any]
            Evaluation result with:
            - symbol: str
            - eligible: bool
            - score: int (0-100)
            - rejection_reasons: List[str]
            - features: Dict[str, Any]
            - regime_context: Dict[str, Any]
        """
        rejection_reasons: List[str] = []
        features: Dict[str, Any] = {
            "price": price,
            "volume": volume,
            "iv_rank": iv_rank,
            "snapshot_age_minutes": snapshot_age_minutes,
            "regime": regime,
        }
        regime_context: Dict[str, Any] = {
            "regime": regime,
        }
        
        # Gates (hard reject)
        if price is None or price <= 0:
            rejection_reasons.append("missing_or_invalid_price")
            return {
                "symbol": symbol,
                "eligible": False,
                "score": 0,
                "rejection_reasons": rejection_reasons,
                "features": features,
                "regime_context": regime_context,
            }
        
        if price < MIN_PRICE or price > MAX_PRICE:
            rejection_reasons.append("price_out_of_range")
            return {
                "symbol": symbol,
                "eligible": False,
                "score": 0,
                "rejection_reasons": rejection_reasons,
                "features": features,
                "regime_context": regime_context,
            }
        
        if regime in ("RISK_OFF", "UNKNOWN"):
            rejection_reasons.append("regime_not_risk_on")
            return {
                "symbol": symbol,
                "eligible": False,
                "score": 0,
                "rejection_reasons": rejection_reasons,
                "features": features,
                "regime_context": regime_context,
            }
        
        # Phase 2B Step 3: Liquidity and IV gates
        if volume is not None and volume < 1_000_000:
            rejection_reasons.append("low_liquidity")
            return {
                "symbol": symbol,
                "eligible": False,
                "score": 0,
                "rejection_reasons": rejection_reasons,
                "features": features,
                "regime_context": regime_context,
            }
        
        if iv_rank is not None and iv_rank < 20:
            rejection_reasons.append("iv_too_low")
            return {
                "symbol": symbol,
                "eligible": False,
                "score": 0,
                "rejection_reasons": rejection_reasons,
                "features": features,
                "regime_context": regime_context,
            }
        
        # Scoring (only if not rejected)
        score_components: Dict[str, float] = {}
        
        # 1. Price suitability (0..30)
        # Highest in [TARGET_LOW..TARGET_HIGH], linear falloff to 0 at bounds [MIN_PRICE..MAX_PRICE]
        if TARGET_LOW <= price <= TARGET_HIGH:
            price_suitability = 30.0
        elif price < TARGET_LOW:
            # Linear from MIN_PRICE to TARGET_LOW
            if price <= MIN_PRICE:
                price_suitability = 0.0
            else:
                price_suitability = 30.0 * (price - MIN_PRICE) / (TARGET_LOW - MIN_PRICE)
        else:  # price > TARGET_HIGH
            # Linear from TARGET_HIGH to MAX_PRICE
            if price >= MAX_PRICE:
                price_suitability = 0.0
            else:
                price_suitability = 30.0 * (MAX_PRICE - price) / (MAX_PRICE - TARGET_HIGH)
        
        score_components["price_suitability"] = price_suitability
        
        # 2. Regime score (0..30)
        if regime == "RISK_ON":
            regime_score = 30.0
        elif regime == "NEUTRAL":
            regime_score = 15.0
        else:
            regime_score = 0.0
        score_components["regime_score"] = regime_score
        
        # 3. Universe priority (0..20)
        # If symbol_universe has priority/tier field use it; else constant 10
        universe_priority = 10.0  # Default constant
        if universe_metadata:
            # Check for priority or tier field (future enhancement)
            if "priority" in universe_metadata:
                # Map priority to score (0-20)
                priority_val = universe_metadata.get("priority", 0)
                universe_priority = min(20.0, max(0.0, float(priority_val) * 2.0))
            elif "tier" in universe_metadata:
                # Map tier to score (tier 1 = 20, tier 2 = 15, tier 3 = 10, etc.)
                tier = universe_metadata.get("tier", 3)
                if tier == 1:
                    universe_priority = 20.0
                elif tier == 2:
                    universe_priority = 15.0
                else:
                    universe_priority = 10.0
        score_components["universe_priority"] = universe_priority
        
        # 4. Freshness (0..20)
        # snapshot_age_minutes: <=60 => 20, <=360 => 10, else 0
        if snapshot_age_minutes <= 60:
            freshness = 20.0
        elif snapshot_age_minutes <= 360:
            freshness = 10.0
        else:
            freshness = 0.0
        score_components["freshness"] = freshness
        
        # 5. IV Rank Score (0..20) - Phase 2B Step 3
        iv_rank_score = 0.0
        if iv_rank is not None:
            if iv_rank >= 50:
                iv_rank_score = 20.0
            elif iv_rank >= 30:
                iv_rank_score = 10.0
            else:
                iv_rank_score = 0.0
        score_components["iv_rank_score"] = iv_rank_score
        
        # 6. Liquidity Bonus (0..10) - Phase 2B Step 3
        liquidity_bonus = 0.0
        if volume is not None:
            if volume >= 10_000_000:
                liquidity_bonus = 10.0
            elif volume >= 3_000_000:
                liquidity_bonus = 5.0
            else:
                liquidity_bonus = 0.0
        score_components["liquidity_bonus"] = liquidity_bonus
        
        # Total score (clamp to [0, 100])
        total_score = sum(score_components.values())
        score = max(0, min(100, int(round(total_score))))
        
        features["score_components"] = score_components
        
        return {
            "symbol": symbol,
            "eligible": True,
            "score": score,
            "rejection_reasons": rejection_reasons,
            "features": features,
            "regime_context": regime_context,
        }
    
    def _recompute_regime(self) -> Optional[Dict[str, Any]]:
        """Recompute regime using snapshot-based price-only logic (Phase 2B).
        
        Uses ONLY the last two snapshots (price-only). Returns UNKNOWN if data missing.
        NO live provider calls.
        
        Returns
        -------
        Optional[Dict[str, Any]]
            Regime result dict with:
            - regime: "BULL", "BEAR", "NEUTRAL", or "UNKNOWN"
            - confidence: 100 (for price-only)
            - details: dict with benchmark info
            - created_at: ISO timestamp
            Or None if computation fails (should not happen - returns UNKNOWN instead).
        """
        try:
            from app.core.market_snapshot import (
                get_latest_snapshot_id,
                get_previous_snapshot_id,
                get_snapshot_prices,
                normalize_symbol,
            )
            from app.core.persistence import upsert_regime
            
            # Step 3: Fetch latest snapshot_id and log it
            latest_id = get_latest_snapshot_id()
            logger.info(f"[HEARTBEAT] Regime recompute: latest_snapshot_id={latest_id}")
            if not latest_id:
                logger.warning("[HEARTBEAT] No latest snapshot available for regime computation")
                return {
                    "regime": "UNKNOWN",
                    "confidence": 0,
                    "details": {"error": "No latest snapshot"},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            
            logger.info(f"[HEARTBEAT] Regime recompute: latest_snapshot_id={latest_id}")
            previous_id = get_previous_snapshot_id(latest_id)
            
            # Bootstrap mode: if no previous snapshot, use latest snapshot only with baseline return = 0
            bootstrap_mode = (previous_id is None)
            
            if bootstrap_mode:
                logger.info("[HEARTBEAT] No previous snapshot - using bootstrap regime calculation (baseline return = 0)")
                # Get prices from latest snapshot only
                prices_s2 = get_snapshot_prices(latest_id)
                
                # Pick benchmark symbol in priority order: SPY, QQQ (SPX typically not in snapshots)
                # Use first found in latest snapshot
                benchmark_candidates = ["SPY", "QQQ"]
                benchmark_symbol = None
                
                for candidate in benchmark_candidates:
                    normalized_candidate = normalize_symbol(candidate)
                    symbol_data = prices_s2.get(normalized_candidate, {})
                    price = symbol_data.get("price") if isinstance(symbol_data, dict) else symbol_data
                    if price is not None and price > 0:
                        benchmark_symbol = normalized_candidate
                        break
                
                if not benchmark_symbol:
                    logger.warning("[HEARTBEAT] No benchmark symbol (SPY/QQQ) found in latest snapshot for bootstrap")
                    return {
                        "regime": "UNKNOWN",
                        "confidence": 0,
                        "details": {"error": "Benchmark symbol missing in bootstrap mode"},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                
                # Bootstrap: assume baseline return = 0 (no prior data)
                benchmark_return = 0.0
                p2 = prices_s2[benchmark_symbol].get("price") if isinstance(prices_s2[benchmark_symbol], dict) else prices_s2[benchmark_symbol]
                p1 = p2  # For bootstrap, p1 = p2 (no change)
                
                if p2 is None or p2 <= 0:
                    logger.warning(f"[HEARTBEAT] Invalid price for {benchmark_symbol} in bootstrap: p2={p2}")
                    return {
                        "regime": "UNKNOWN",
                        "confidence": 0,
                        "details": {"error": f"Invalid price for {benchmark_symbol} in bootstrap"},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
            else:
                # Normal mode: use both snapshots
                # Get prices from both snapshots
                prices_s2 = get_snapshot_prices(latest_id)
                prices_s1 = get_snapshot_prices(previous_id)
                
                # Benchmark presence: check only the latest snapshot; warn only if SPY and QQQ both missing
                symbols_in_latest = set(prices_s2.keys())
                spy_ok = normalize_symbol("SPY") in symbols_in_latest
                qqq_ok = normalize_symbol("QQQ") in symbols_in_latest
                if not spy_ok and not qqq_ok:
                    logger.warning("[HEARTBEAT] Benchmarks missing from latest snapshot: SPY, QQQ")
                
                # Pick benchmark symbol in priority order: SPX, SPY, QQQ
                # Use first found in BOTH snapshots (for return computation)
                benchmark_candidates = ["SPX", "SPY", "QQQ"]
                benchmark_symbol = None
                
                for candidate in benchmark_candidates:
                    normalized_candidate = normalize_symbol(candidate)
                    s2_data = prices_s2.get(normalized_candidate, {})
                    s1_data = prices_s1.get(normalized_candidate, {})
                    p2_val = s2_data.get("price") if isinstance(s2_data, dict) else s2_data
                    p1_val = s1_data.get("price") if isinstance(s1_data, dict) else s1_data
                    if p2_val is not None and p1_val is not None:
                        benchmark_symbol = normalized_candidate
                        break
                
                if not benchmark_symbol:
                    logger.warning("[HEARTBEAT] No benchmark symbol with data in both snapshots")
                    return {
                        "regime": "UNKNOWN",
                        "confidence": 0,
                        "details": {"error": "Benchmark symbol missing"},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                
                # Get prices
                s2_data = prices_s2[benchmark_symbol]
                s1_data = prices_s1[benchmark_symbol]
                p2 = s2_data.get("price") if isinstance(s2_data, dict) else s2_data
                p1 = s1_data.get("price") if isinstance(s1_data, dict) else s1_data
                
                if p1 is None or p2 is None or p1 <= 0:
                    logger.warning(f"[HEARTBEAT] Invalid prices for {benchmark_symbol}: p1={p1}, p2={p2}")
                    return {
                        "regime": "UNKNOWN",
                        "confidence": 0,
                        "details": {"error": f"Invalid prices for {benchmark_symbol}"},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                
                # Compute return = (p2 - p1) / p1
                benchmark_return = (p2 - p1) / p1
            
            # Determine regime based on thresholds
            if benchmark_return >= 0.0015:  # >= +0.15%
                regime = "BULL"
            elif benchmark_return <= -0.0015:  # <= -0.15%
                regime = "BEAR"
            else:
                regime = "NEUTRAL"
            
            # Log regime inputs and result
            mode_str = "bootstrap" if bootstrap_mode else "normal"
            logger.info(
                f"[HEARTBEAT] Regime computation ({mode_str}): benchmark={benchmark_symbol}, "
                f"p1={p1:.2f}, p2={p2:.2f}, return={benchmark_return:.4f}, regime={regime}"
            )
            
            # Use ET timezone for created_at
            if _ET_TZ:
                created_at = datetime.now(_ET_TZ)
            else:
                created_at = datetime.now(timezone.utc)
            
            computed_at = created_at.isoformat()
            
            # Step 3: Persist regime for snapshot_id S2 and log insertion
            upsert_regime(
                snapshot_id=latest_id,
                regime=regime,
                benchmark_symbol=benchmark_symbol,
                benchmark_return=benchmark_return,
                computed_at=computed_at,
            )
            logger.info(
                f"[HEARTBEAT] wrote market_regimes snapshot_id={latest_id} regime={regime} "
                f"benchmark={benchmark_symbol} return={benchmark_return:.4f}"
            )
            
            return {
                "regime": regime,
                "confidence": 100,  # Price-only is deterministic
                "details": {
                    "benchmark_symbol": benchmark_symbol,
                    "benchmark_return": benchmark_return,
                    "p1": p1,
                    "p2": p2,
                    "method": "snapshot_price_only_bootstrap" if bootstrap_mode else "snapshot_price_only",
                },
                "created_at": computed_at,
            }
        except Exception as e:
            logger.error(f"[HEARTBEAT] Failed to recompute regime: {e}", exc_info=True)
            # Return UNKNOWN instead of None to avoid breaking the cycle
            return {
                "regime": "UNKNOWN",
                "confidence": 0,
                "details": {"error": str(e)},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
    
    def _get_snapshot_data(self) -> tuple[Dict[str, Any], Optional[datetime], float]:
        """Get market data from active frozen snapshot (Phase 2A).
        
        Returns
        -------
        tuple[Dict[str, Any], Optional[datetime], float]
            (symbol_to_df dict, snapshot timestamp, data age in minutes)
        """
        try:
            from app.core.market_snapshot import get_active_snapshot, load_snapshot_data
            
            snapshot = get_active_snapshot()
            if not snapshot:
                return {}, None, 0.0
            
            snapshot_id = snapshot["snapshot_id"]
            snapshot_timestamp_et = snapshot["snapshot_timestamp_et"]
            data_age_minutes = snapshot["data_age_minutes"]
            
            # Load snapshot data
            symbol_to_df = load_snapshot_data(snapshot_id)
            
            # Parse snapshot timestamp
            try:
                data_timestamp = datetime.fromisoformat(snapshot_timestamp_et)
                data_timestamp = ensure_et_aware(data_timestamp)
            except Exception:
                data_timestamp = None
            
            # Filter to only symbols with data (remove None entries)
            symbol_to_df = {k: v for k, v in symbol_to_df.items() if v is not None}
            
            if symbol_to_df:
                logger.info(
                    f"[SNAPSHOT] Using frozen snapshot {snapshot_id[:8]}... "
                    f"({len(symbol_to_df)} symbols, age: {data_age_minutes:.1f} min)"
                )
            
            return symbol_to_df, data_timestamp, data_age_minutes
        
        except Exception as e:
            logger.error(f"[HEARTBEAT] Failed to load snapshot: {e}")
            return {}, None, 0.0
    
    def _get_market_data_with_staleness(
        self,
        symbols: List[str]
    ) -> tuple[Dict[str, Any], Optional[datetime], float]:
        """Get market data with staleness info (NO Streamlit calls).
        
        Returns
        -------
        tuple[Dict[str, Any], Optional[datetime], float]
            (symbol_to_df dict, latest data timestamp, max staleness in minutes)
        """
        with self._cache_lock:
            # Get current time in ET
            if _ET_TZ:
                now = datetime.now(_ET_TZ)
            else:
                now = ensure_et_aware(datetime.now(timezone.utc))
            
            if now is None:
                logger.error("[HEARTBEAT] Failed to get current time in ET")
                return {}, None, 0.0
            
            stale_threshold = timedelta(minutes=MARKET_DATA_STALE_THRESHOLD_MINUTES)
            
            # Check cache freshness
            cache_needs_refresh = False
            max_staleness_minutes = 0.0
            latest_timestamp = None
            
            for symbol in symbols:
                if symbol not in self._market_data_cache:
                    cache_needs_refresh = True
                    break
                
                cache_entry = self._market_data_cache[symbol]
                cached_at_str = cache_entry.get("cached_at")
                
                if cached_at_str is None:
                    logger.warning(f"[HEARTBEAT] Cache entry for {symbol} has no cached_at, forcing refresh")
                    cache_needs_refresh = True
                    break
                
                try:
                    cache_time = datetime.fromisoformat(cached_at_str)
                    cache_time_et = ensure_et_aware(cache_time)
                    
                    if cache_time_et is None:
                        logger.warning(f"[HEARTBEAT] Failed to normalize cache_time for {symbol}, forcing refresh")
                        cache_needs_refresh = True
                        break
                    
                    age_minutes = (now - cache_time_et).total_seconds() / 60.0
                    max_staleness_minutes = max(max_staleness_minutes, age_minutes)
                    
                    if now - cache_time_et > stale_threshold:
                        cache_needs_refresh = True
                    else:
                        if latest_timestamp is None or cache_time_et > latest_timestamp:
                            latest_timestamp = cache_time_et
                except (ValueError, TypeError) as e:
                    logger.warning(f"[HEARTBEAT] Failed to parse cached_at '{cached_at_str}' for {symbol}: {e}")
                    cache_needs_refresh = True
                    break
            
            # Use cache if fresh
            if not cache_needs_refresh:
                logger.debug(f"[HEARTBEAT] Using cached market data for {len(symbols)} symbols")
                return {
                    symbol: self._market_data_cache[symbol]["data"]
                    for symbol in symbols
                    if symbol in self._market_data_cache
                }, latest_timestamp, max_staleness_minutes
            
            # Fetch fresh data
            logger.info(f"[HEARTBEAT] Fetching fresh market data for {len(symbols)} symbols")
            try:
                from app.core.market_data.factory import get_market_data_provider
                
                provider = get_market_data_provider()
                symbol_to_df = {}
                fetch_timestamp = now  # Already ET-aware
                
                for symbol in symbols:
                    try:
                        df = provider.get_daily(symbol, lookback=300)
                        symbol_to_df[symbol] = df
                        
                        # Update cache with ET timestamp
                        self._market_data_cache[symbol] = {
                            "data": df,
                            "cached_at": now.isoformat(),
                        }
                    except Exception as e:
                        logger.warning(f"[HEARTBEAT] Failed to fetch {symbol}: {e}")
                        # Use cached data if available, even if stale
                        if symbol in self._market_data_cache:
                            symbol_to_df[symbol] = self._market_data_cache[symbol]["data"]
                            cached_at_str = self._market_data_cache[symbol].get("cached_at")
                            if cached_at_str:
                                try:
                                    cache_time = datetime.fromisoformat(cached_at_str)
                                    cache_time_et = ensure_et_aware(cache_time)
                                    if cache_time_et:
                                        age_minutes = (now - cache_time_et).total_seconds() / 60.0
                                        max_staleness_minutes = max(max_staleness_minutes, age_minutes)
                                        if latest_timestamp is None or cache_time_et > latest_timestamp:
                                            latest_timestamp = cache_time_et
                                except (ValueError, TypeError) as e:
                                    logger.debug(f"[HEARTBEAT] Could not parse cached_at for {symbol}: {e}")
                
                if symbol_to_df:
                    latest_timestamp = fetch_timestamp
                    max_staleness_minutes = 0.0
                
                return symbol_to_df, latest_timestamp, max_staleness_minutes
            
            except Exception as e:
                logger.error(f"[HEARTBEAT] Failed to fetch market data: {e}")
                # Fallback to cache even if stale
                return {
                    symbol: self._market_data_cache[symbol]["data"]
                    for symbol in symbols
                    if symbol in self._market_data_cache
                }, latest_timestamp, max_staleness_minutes
    
    def _update_daily_tracking(self, actionable_candidates: List[Dict[str, Any]]) -> None:
        """Update daily candidate tracking (ET date, upsert per day).
        
        Parameters
        ----------
        actionable_candidates:
            List of actionable candidates.
        """
        try:
            from app.core.config.paths import DB_PATH
            import sqlite3
            
            # Get ET date (not UTC)
            if pytz:
                et_tz = pytz.timezone("America/New_York")
                et_now = datetime.now(et_tz)
                et_date = et_now.date().isoformat()
            else:
                # Fallback to UTC if pytz not available
                et_date = datetime.now(timezone.utc).date().isoformat()
            
            count = len(actionable_candidates)
            db_path = DB_PATH
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            try:
                # Ensure table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS candidate_daily_tracking (
                        date TEXT PRIMARY KEY,
                        candidate_count INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                
                created_at = datetime.now(timezone.utc).isoformat()
                
                # Upsert (insert or replace)
                cursor.execute("""
                    INSERT OR REPLACE INTO candidate_daily_tracking (date, candidate_count, created_at, updated_at)
                    VALUES (?, ?, 
                        COALESCE((SELECT created_at FROM candidate_daily_tracking WHERE date = ?), ?),
                        ?)
                """, (et_date, count, et_date, created_at, created_at))
                
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"[HEARTBEAT] Failed to update daily tracking: {e}")
    
    def _detect_state_changes(
        self,
        actionable_candidates: List[Dict[str, Any]],
        regime: str
    ) -> int:
        """Detect state changes and emit alerts (only on changes, with rate limits).
        
        Parameters
        ----------
        actionable_candidates:
            List of actionable candidates.
        regime:
            Current market regime.
        
        Returns
        -------
        int
            Number of alerts emitted.
        """
        alerts_count = 0
        
        try:
            from app.core.persistence import create_alert
            
            # Skip alerts on first cycle (no previous state to compare)
            is_first_cycle = self._previous_regime is None
            
            if is_first_cycle:
                logger.debug("[HEARTBEAT] First cycle - skipping state change alerts")
                return 0
            
            # Detect candidate changes
            current_symbols = {c["symbol"] for c in actionable_candidates}
            
            # New candidates appeared (alert on each new symbol)
            new_symbols = current_symbols - self._previous_candidate_symbols
            if new_symbols:
                for symbol in new_symbols:
                    create_alert(
                        f"New CSP opportunity: {symbol}",
                        level="INFO"
                    )
                    alerts_count += 1
            
            # Candidates disappeared (rate-limited: max once per 6 hours)
            removed_symbols = self._previous_candidate_symbols - current_symbols
            if removed_symbols:
                # Get current time in ET
                if _ET_TZ:
                    now = datetime.now(_ET_TZ)
                else:
                    now = ensure_et_aware(datetime.now(timezone.utc))
                
                if now is None:
                    logger.warning("[HEARTBEAT] Failed to get current time for removal alert check")
                    now = datetime.now(timezone.utc)  # Fallback
                    now = ensure_et_aware(now)
                
                should_alert = False
                
                if self._last_removal_alert_time is None:
                    should_alert = True
                else:
                    # Ensure both are ET-aware for comparison
                    last_alert_et = ensure_et_aware(self._last_removal_alert_time)
                    if last_alert_et is None or now is None:
                        logger.warning("[HEARTBEAT] Failed to normalize timestamps for removal alert check")
                        should_alert = True
                    else:
                        hours_since_last = (now - last_alert_et).total_seconds() / 3600.0
                        if hours_since_last >= CANDIDATE_REMOVAL_ALERT_COOLDOWN_HOURS:
                            should_alert = True
                
                if should_alert:
                    # Summarized alert (one alert for all removals)
                    create_alert(
                        f"CSP opportunities removed: {', '.join(sorted(removed_symbols))}",
                        level="INFO"
                    )
                    # Store as ET-aware datetime
                    self._last_removal_alert_time = ensure_et_aware(now) if now else None
                    alerts_count += 1
            
            # Regime change (always alert)
            if self._previous_regime != regime:
                create_alert(
                    f"Market regime changed: {self._previous_regime} → {regime}",
                    level="WATCH"
                )
                alerts_count += 1
            
            return alerts_count
        
        except Exception as e:
            logger.error(f"[HEARTBEAT] Error detecting state changes: {e}")
            return 0


__all__ = [
    "HeartbeatManager",
    "HEARTBEAT_INTERVAL_SECONDS",
    "MARKET_DATA_STALE_THRESHOLD_MINUTES",
    "REGIME_STALE_THRESHOLD_MINUTES",
    "DATA_STALE_HALT_THRESHOLD_MINUTES",
    "CANDIDATE_REMOVAL_ALERT_COOLDOWN_HOURS",
    "ensure_et_aware",
]
