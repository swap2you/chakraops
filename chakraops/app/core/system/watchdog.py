# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.3: Scheduler watchdog and health checks. Non-blocking; must not crash system."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def check_scheduler_health(
    last_run_timestamp: Optional[str],
    interval_minutes: int,
) -> Optional[Dict[str, Any]]:
    """
    If now - last_run > (interval_minutes * 2) -> return HEALTH alert payload for SCHEDULER_STALLED.
    Otherwise return None. Non-blocking; does not send anything.
    """
    if not last_run_timestamp or interval_minutes <= 0:
        return None
    try:
        last_ts = datetime.fromisoformat(last_run_timestamp.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None
    now = datetime.now(timezone.utc).timestamp()
    threshold_sec = interval_minutes * 2 * 60
    if (now - last_ts) <= threshold_sec:
        return None
    return {
        "reason": "SCHEDULER_STALLED",
        "failed_symbols": ["SCHEDULER"],
        "failed": "SCHEDULER_STALLED",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "last_run": last_run_timestamp,
        "interval_minutes": interval_minutes,
    }


def check_eval_wall_time(
    wall_time_sec: float,
    cycle_minutes: int,
) -> Optional[Dict[str, Any]]:
    """
    Phase 8.8: If wall time > 25% of cycle length -> WARN (HEALTH advisory).
    """
    if cycle_minutes <= 0:
        return None
    cycle_sec = cycle_minutes * 60
    threshold = 0.25 * cycle_sec
    if wall_time_sec <= threshold:
        return None
    return {
        "reason": "EVAL_WALL_TIME_HIGH",
        "failed_symbols": ["EVAL_BUDGET"],
        "failed": "EVAL_WALL_TIME_HIGH",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "wall_time_sec": wall_time_sec,
        "cycle_minutes": cycle_minutes,
        "threshold_pct": 25,
    }


def check_cache_hit_rate(cache_hit_rate_pct: Optional[float]) -> Optional[Dict[str, Any]]:
    """
    Phase 8.8: If cache hit rate < 20% after warmup -> WARN (HEALTH advisory).
    Informational only; no blocking.
    """
    if cache_hit_rate_pct is None:
        return None
    try:
        if float(cache_hit_rate_pct) >= 20.0:
            return None
    except (TypeError, ValueError):
        return None
    return {
        "reason": "CACHE_HIT_RATE_LOW",
        "failed_symbols": ["CACHE"],
        "failed": "CACHE_HIT_RATE_LOW",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "cache_hit_rate_pct": cache_hit_rate_pct,
    }


def check_orats_latency(rolling_avg_ms: Optional[float]) -> Optional[Dict[str, Any]]:
    """
    If ORATS latency rolling average > 6000 ms, return HEALTH alert payload for ORATS_LATENCY_HIGH.
    Otherwise return None. Caller is responsible for tracking rolling 5; this only checks the value.
    """
    if rolling_avg_ms is None:
        return None
    try:
        if float(rolling_avg_ms) <= 6000:
            return None
    except (TypeError, ValueError):
        return None
    return {
        "reason": "ORATS_LATENCY_HIGH",
        "failed_symbols": ["ORATS"],
        "failed": "ORATS_LATENCY_HIGH",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "rolling_avg_ms": rolling_avg_ms,
    }


def check_signals_24h(has_signals_in_24h: bool) -> Optional[Dict[str, Any]]:
    """
    If no signals generated in 24h, return DAILY advisory payload (not critical).
    Otherwise return None.
    """
    if has_signals_in_24h:
        return None
    return {
        "reason": "NO_SIGNALS_24H",
        "channel": "DAILY",
        "top_signals": [],
        "open_positions_count": None,
        "total_capital_used": None,
        "exposure_pct": None,
        "average_premium_capture": None,
        "exit_alerts_today": 0,
        "alerts_count": 0,
    }


def run_watchdog_checks(
    last_run_timestamp: Optional[str],
    interval_minutes: int,
    orats_rolling_avg_ms: Optional[float] = None,
    has_signals_in_24h: bool = True,
    wall_time_sec: Optional[float] = None,
    cache_hit_rate_pct: Optional[float] = None,
) -> None:
    """
    Run all watchdog checks and send Slack alerts if needed. Non-blocking; catches all exceptions.
    Integrate into scheduler cycle or health_gate. Does not crash.
    """
    try:
        from app.core.alerts.slack_dispatcher import route_alert
    except ImportError:
        return
    # SCHEDULER_STALLED -> HEALTH
    payload = check_scheduler_health(last_run_timestamp, interval_minutes)
    if payload:
        try:
            route_alert(
                "HEALTH",
                payload,
                event_key="health:scheduler_stalled",
                state_path="artifacts/alerts/last_sent_state.json",
            )
        except Exception as e:
            logger.warning("[Watchdog] SCHEDULER_STALLED alert failed: %s", e)
    # ORATS_LATENCY_HIGH -> HEALTH
    payload = check_orats_latency(orats_rolling_avg_ms)
    if payload:
        try:
            route_alert(
                "HEALTH",
                payload,
                event_key="health:orats_latency",
                state_path="artifacts/alerts/last_sent_state.json",
            )
        except Exception as e:
            logger.warning("[Watchdog] ORATS_LATENCY alert failed: %s", e)
    # Phase 8.8: EVAL_WALL_TIME_HIGH -> HEALTH
    if wall_time_sec is not None and interval_minutes > 0:
        payload = check_eval_wall_time(wall_time_sec, interval_minutes)
        if payload:
            try:
                route_alert(
                    "HEALTH",
                    payload,
                    event_key="health:eval_wall_time",
                    state_path="artifacts/alerts/last_sent_state.json",
                )
            except Exception as e:
                logger.warning("[Watchdog] EVAL_WALL_TIME alert failed: %s", e)
    # Phase 8.8: CACHE_HIT_RATE_LOW -> HEALTH
    payload = check_cache_hit_rate(cache_hit_rate_pct)
    if payload:
        try:
            route_alert(
                "HEALTH",
                payload,
                event_key="health:cache_hit_rate",
                state_path="artifacts/alerts/last_sent_state.json",
            )
        except Exception as e:
            logger.warning("[Watchdog] CACHE_HIT_RATE alert failed: %s", e)
    # NO_SIGNALS_24H -> DAILY advisory
    payload = check_signals_24h(has_signals_in_24h)
    if payload:
        try:
            route_alert(
                "DAILY",
                {**payload, "top_signals": payload.get("top_signals") or [], "open_positions_count": 0},
                event_key="daily:no_signals_24h",
                state_path="artifacts/alerts/last_sent_state.json",
            )
        except Exception as e:
            logger.warning("[Watchdog] NO_SIGNALS_24H alert failed: %s", e)
