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

# Process-level singleton (module global)
_process_instance: Optional[HeartbeatManager] = None
_process_lock = threading.Lock()


class HeartbeatManager:
    """Manages background evaluation heartbeat.
    
    Thread-safe singleton that runs evaluation cycles in background.
    Uses process-level singleton to prevent duplicate threads across Streamlit reruns.
    """
    
    def __init__(self):
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
    
    def _evaluate_cycle(self) -> tuple[int, int]:
        """Run one evaluation cycle (NO Streamlit calls).
        
        Returns
        -------
        tuple[int, int]
            (candidates_count, alerts_count)
        """
        try:
            # Step 1: Get or compute regime (check freshness)
            regime_result, regime_age_minutes = self._get_regime_with_age()
            if not regime_result:
                logger.warning("[HEARTBEAT] No regime data available, skipping cycle")
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
            
            # Step 2: Get enabled symbols
            from app.core.persistence import get_enabled_symbols
            symbols = get_enabled_symbols()
            if not symbols:
                logger.warning("[HEARTBEAT] No enabled symbols, skipping cycle")
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
            
            # Step 3: Get market data (use cache if fresh, check staleness)
            symbol_to_df, data_timestamp, data_stale_minutes = self._get_market_data_with_staleness(symbols)
            if not symbol_to_df:
                logger.warning("[HEARTBEAT] No market data available, skipping cycle")
                self._update_health("NO_DATA")
                with self._health_lock:
                    self._last_cycle_eval = {
                        "symbols_evaluated": len(symbols),
                        "csp_candidates_count": 0,
                        "rejected_symbols_count": len(symbols),
                        "rejection_reasons": {"No market data available": len(symbols)},
                        "market_data_age_minutes": data_stale_minutes if data_stale_minutes else 0.0,
                        "enabled_universe_size": len(symbols),
                    }
                return 0, 0
            
            # Check data staleness and emit alert if needed
            if data_stale_minutes > DATA_STALE_HALT_THRESHOLD_MINUTES:
                from app.core.persistence import create_alert
                create_alert(
                    f"Market data is stale ({data_stale_minutes:.1f} minutes old). System may be using outdated data.",
                    level="HALT"
                )
            elif data_stale_minutes > MARKET_DATA_STALE_THRESHOLD_MINUTES:
                from app.core.persistence import create_alert
                create_alert(
                    f"Market data is stale ({data_stale_minutes:.1f} minutes old).",
                    level="WATCH"
                )
            
            # Step 4: Find CSP candidates
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
            symbols_evaluated = len(symbols)
            
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
            symbols_without_candidates = symbols_evaluated - len(symbols_with_candidates)
            if symbols_without_candidates > 0:
                reason = "No CSP candidates found"
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + symbols_without_candidates
            
            # Step 6: Log candidates to database
            log_csp_candidates(candidates)
            
            # Step 7: Update daily tracking (ET date)
            self._update_daily_tracking(actionable_candidates)
            
            # Step 8: Detect state changes and emit alerts
            alerts_count = self._detect_state_changes(actionable_candidates, regime)
            
            # Step 9: Update previous state
            self._previous_candidate_symbols = {
                c["symbol"] for c in actionable_candidates
            }
            self._previous_regime = regime
            
            # Step 10: Update cycle evaluation details
            with self._health_lock:
                self._last_cycle_eval = {
                    "symbols_evaluated": symbols_evaluated,
                    "csp_candidates_count": len(candidates),
                    "rejected_symbols_count": symbols_without_candidates + blocked_count,
                    "rejection_reasons": rejection_reasons,
                    "market_data_age_minutes": data_stale_minutes,
                    "enabled_universe_size": symbols_evaluated,
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
        """Get regime snapshot with age in minutes (from database).
        
        Returns
        -------
        tuple[Optional[Dict[str, Any]], float]
            (Regime result dict, age in minutes) or (None, 0.0) if not available.
        """
        try:
            from app.db.database import get_db_path
            import sqlite3
            
            db_path = get_db_path()
            if not db_path.exists():
                return None, 0.0
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT regime, confidence, details, created_at
                FROM regime_snapshots
                ORDER BY created_at DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                import json
                created_at_str = row[3]
                
                if created_at_str is None:
                    logger.warning("[HEARTBEAT] Regime created_at is None, cannot compute age")
                    return {
                        "regime": row[0],
                        "confidence": row[1],
                        "details": json.loads(row[2]) if row[2] else {},
                        "created_at": created_at_str,
                    }, 0.0
                
                # Parse and normalize to ET
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    created_at_et = ensure_et_aware(created_at)
                    
                    # Get current time in ET
                    if _ET_TZ:
                        now_et = datetime.now(_ET_TZ)
                    else:
                        now_et = ensure_et_aware(datetime.now(timezone.utc))
                    
                    if created_at_et is None or now_et is None:
                        logger.warning("[HEARTBEAT] Failed to normalize timestamps for regime age calculation")
                        return {
                            "regime": row[0],
                            "confidence": row[1],
                            "details": json.loads(row[2]) if row[2] else {},
                            "created_at": created_at_str,
                        }, 0.0
                    
                    age_minutes = (now_et - created_at_et).total_seconds() / 60.0
                except (ValueError, TypeError) as e:
                    logger.warning(f"[HEARTBEAT] Failed to parse regime created_at '{created_at_str}': {e}")
                    return {
                        "regime": row[0],
                        "confidence": row[1],
                        "details": json.loads(row[2]) if row[2] else {},
                        "created_at": created_at_str,
                    }, 0.0
                
                return {
                    "regime": row[0],
                    "confidence": row[1],
                    "details": json.loads(row[2]) if row[2] else {},
                    "created_at": created_at_str,
                }, age_minutes
            
            return None, 0.0
        except Exception as e:
            logger.error(f"[HEARTBEAT] Failed to get regime: {e}")
            return None, 0.0
    
    def _recompute_regime(self) -> Optional[Dict[str, Any]]:
        """Recompute regime (NO Streamlit calls).
        
        Returns
        -------
        Optional[Dict[str, Any]]
            Regime result dict, or None if recomputation fails.
        """
        try:
            from app.core.market_data.factory import get_market_data_provider
            from app.core.regime import build_weekly_from_daily, compute_regime
            from app.db.database import log_regime_snapshot, get_db_path
            import sqlite3
            
            provider = get_market_data_provider()
            df_spy_daily = provider.get_daily("SPY", lookback=400)
            df_spy_weekly = build_weekly_from_daily(df_spy_daily)
            regime_result = compute_regime(df_spy_daily, df_spy_weekly, require_weekly_confirm=True)
            
            # Log regime snapshot
            log_regime_snapshot(
                regime_result["regime"],
                regime_result["confidence"],
                regime_result["details"]
            )
            
            logger.info(f"[HEARTBEAT] Recomputed regime: {regime_result['regime']} (confidence: {regime_result['confidence']}%)")
            
            # Use ET timezone for created_at
            if _ET_TZ:
                created_at = datetime.now(_ET_TZ)
            else:
                created_at = datetime.now(timezone.utc)
            
            return {
                "regime": regime_result["regime"],
                "confidence": regime_result["confidence"],
                "details": regime_result["details"],
                "created_at": created_at.isoformat(),
            }
        except Exception as e:
            logger.error(f"[HEARTBEAT] Failed to recompute regime: {e}")
            return None
    
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
            from app.db.database import get_db_path
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
            db_path = get_db_path()
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
