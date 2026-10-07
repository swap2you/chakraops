# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.3: Scheduler watchdog and health checks. Non-blocking; must not crash system."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Phase 8.6: Restart grace window — do not emit SCHEDULER_MISSED for first N minutes after backend start.
RESTART_GRACE_MINUTES = 10


def _is_market_open() -> bool:
    """True if US market (America/New_York) is in trading hours 9:30–16:00 ET."""
    try:
        from app.market.market_hours import is_market_open
        return is_market_open()
    except Exception:
        return False


def check_scheduler_health(
    last_run_timestamp: Optional[str],
    interval_minutes: int,
    app_start_time_utc: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    If now - last_run > (interval_minutes * 2) -> return HEALTH alert payload for SCHEDULER_STALLED.
    Otherwise return None. Non-blocking; does not send anything.

    Phase 8.6 gating:
    - Restart grace: do not emit if now < app_start + 10 minutes.
    - Market-hours: do not emit WARN/FAIL if US market is closed (skip; no downgrade needed).
    """
    if not last_run_timestamp or interval_minutes <= 0:
        return None
    now_ts = datetime.now(timezone.utc).timestamp()
    # Restart grace: skip for first 10 minutes after backend start
    if app_start_time_utc is not None:
        grace_sec = RESTART_GRACE_MINUTES * 60
        if (now_ts - app_start_time_utc) < grace_sec:
            return None
    # Market-hours: do not emit when market closed (avoids false WARN after hours)
    if not _is_market_open():
        return None
    try:
        last_ts = datetime.fromisoformat(last_run_timestamp.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None
    threshold_sec = interval_minutes * 2 * 60
    if (now_ts - last_ts) <= threshold_sec:
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


def check_requests_vs_budget(
    requests_estimated: Optional[int],
    max_requests_estimate: Optional[int],
) -> Optional[Dict[str, Any]]:
    """
    Phase 8.9: If requests_estimated > 80% of max_requests_estimate -> WARN (HEALTH advisory).
    """
    if requests_estimated is None or max_requests_estimate is None or max_requests_estimate <= 0:
        return None
    try:
        req = int(requests_estimated)
        max_r = int(max_requests_estimate)
    except (TypeError, ValueError):
        return None
    if req <= int(0.8 * max_r):
        return None
    return {
        "reason": "REQUESTS_ESTIMATE_HIGH",
        "failed_symbols": ["EVAL_BUDGET"],
        "failed": "REQUESTS_ESTIMATE_HIGH",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "requests_estimated": req,
        "max_requests_estimate": max_r,
    }


def check_cache_hit_rate_hot_endpoint(
    cache_stats_by_endpoint: Optional[Dict[str, Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """
    Phase 8.9: If cores or strikes endpoint has low hit rate (<20%) and traffic -> WARN.
    """
    if not cache_stats_by_endpoint:
        return None
    hot_endpoints = ("cores", "strikes")
    for ep in hot_endpoints:
        stats = cache_stats_by_endpoint.get(ep)
        if not stats:
            continue
        hits = stats.get("hits", 0) or 0
        misses = stats.get("misses", 0) or 0
        total = hits + misses
        if total < 5:
            continue
        hit_rate = 100.0 * hits / total
        if hit_rate < 20.0:
            return {
                "reason": "CACHE_HIT_RATE_LOW_HOT_ENDPOINT",
                "failed_symbols": ["CACHE"],
                "failed": "CACHE_HIT_RATE_LOW_HOT_ENDPOINT",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "endpoint": ep,
                "cache_hit_rate_pct": round(hit_rate, 1),
            }
    return None


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
    requests_estimated: Optional[int] = None,
    max_requests_estimate: Optional[int] = None,
    cache_stats_by_endpoint: Optional[Dict[str, Dict[str, Any]]] = None,
    app_start_time_utc: Optional[float] = None,
) -> None:
    """
    Run all watchdog checks and send Slack alerts if needed. Non-blocking; catches all exceptions.
    Integrate into scheduler cycle or health_gate. Does not crash.
    """
    try:
        from app.core.alerts.slack_dispatcher import route_alert
    except ImportError:
        return
    # SCHEDULER_STALLED -> HEALTH (gated by restart grace + market hours)
    payload = check_scheduler_health(last_run_timestamp, interval_minutes, app_start_time_utc)
    if payload:
        try:
            from app.api.notifications_store import append_notification
            append_notification(
                "WARN",
                "SCHEDULER_MISSED",
                "Scheduler missed window; last run too old",
                details=payload,
                subtype="SCHEDULER_MISSED",
            )
        except Exception as e:
            logger.debug("[Watchdog] Failed to append SCHEDULER_MISSED notification: %s", e)
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
    # Phase 8.9: REQUESTS_ESTIMATE_HIGH -> HEALTH
    payload = check_requests_vs_budget(requests_estimated, max_requests_estimate)
    if payload:
        try:
            route_alert(
                "HEALTH",
                payload,
                event_key="health:requests_estimate",
                state_path="artifacts/alerts/last_sent_state.json",
            )
        except Exception as e:
            logger.warning("[Watchdog] REQUESTS_ESTIMATE alert failed: %s", e)
    # Phase 8.9: CACHE_HIT_RATE_LOW_HOT_ENDPOINT -> HEALTH
    payload = check_cache_hit_rate_hot_endpoint(cache_stats_by_endpoint)
    if payload:
        try:
            route_alert(
                "HEALTH",
                payload,
                event_key="health:cache_hit_rate_hot_endpoint",
                state_path="artifacts/alerts/last_sent_state.json",
            )
        except Exception as e:
            logger.warning("[Watchdog] CACHE_HIT_RATE_HOT_ENDPOINT alert failed: %s", e)
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


def collect_watchdog_warnings(
    last_run_timestamp: Optional[str] = None,
    interval_minutes: int = 30,
    orats_rolling_avg_ms: Optional[float] = None,
    has_signals_in_24h: bool = True,
    wall_time_sec: Optional[float] = None,
    cache_hit_rate_pct: Optional[float] = None,
    requests_estimated: Optional[int] = None,
    max_requests_estimate: Optional[int] = None,
    cache_stats_by_endpoint: Optional[Dict[str, Dict[str, Any]]] = None,
    app_start_time_utc: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Run all watchdog checks and return any warning payloads (without sending alerts).
    Used by UI-1 diagnostics persistence.
    """
    warnings: List[Dict[str, Any]] = []
    for fn, args in [
        (check_scheduler_health, (last_run_timestamp, interval_minutes, app_start_time_utc)),
        (check_orats_latency, (orats_rolling_avg_ms,)),
        (check_eval_wall_time, (wall_time_sec or 0, interval_minutes)),
        (check_cache_hit_rate, (cache_hit_rate_pct,)),
        (check_requests_vs_budget, (requests_estimated, max_requests_estimate)),
        (check_cache_hit_rate_hot_endpoint, (cache_stats_by_endpoint,)),
        (check_signals_24h, (has_signals_in_24h,)),
    ]:
        try:
            p = fn(*args)
            if p:
                warnings.append(p)
        except Exception:
            pass
    return warnings
