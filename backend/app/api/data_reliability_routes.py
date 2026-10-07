# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Read-only R32.0 data-reliability API.

Exposes provider health, freshness/cache/retry/rate-limit policy, weekly
universe-refresh determinism, refresh history, and explicit event/earnings
calendar availability. All endpoints are GET and side-effect free; none route
orders, return secrets, or introduce a fallback provider. Mounted under the
public ``/api/ui`` prefix.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/data-reliability/health")
def get_data_reliability_health() -> dict:
    """Provider health, policies, contract validation, and calendar state."""
    from app.core.data_reliability.provider_health import provider_health_snapshot
    from app.core.data_reliability.event_calendar_status import (
        earnings_calendar_status,
        event_calendar_status,
    )

    provider = provider_health_snapshot()
    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "event_calendar": event_calendar_status().to_dict(),
        "earnings_calendar": earnings_calendar_status(
            token_present=provider.get("token_present")
        ).to_dict(),
    }


@router.get("/data-reliability/universe/weekly")
def get_weekly_universe() -> dict:
    """Deterministic weekly universe for the current manifest and date."""
    from app.core.universe.universe_manager import load_universe_manifest
    from app.core.universe.weekly_refresh import (
        compute_weekly_universe,
        weekly_refresh_due,
    )
    from app.core.universe.refresh_history_store import RefreshHistoryStore

    manifest = load_universe_manifest()
    today = date.today()
    store = RefreshHistoryStore()
    last = store.last()
    previous_symbols = (last or {}).get("symbols") if last else None
    last_run_date: Optional[date] = None
    if last and last.get("run_at_utc"):
        try:
            last_run_date = datetime.fromisoformat(
                str(last["run_at_utc"]).replace("Z", "+00:00")
            ).date()
        except (ValueError, TypeError):
            last_run_date = None

    result = compute_weekly_universe(manifest, today, previous_symbols=previous_symbols)
    payload = result.to_dict()
    payload["refresh_due"] = weekly_refresh_due(last_run_date, today)
    payload["last_refresh_at_utc"] = (last or {}).get("run_at_utc") if last else None
    return payload


@router.get("/data-reliability/universe/refresh-history")
def get_refresh_history(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    """Recent weekly-refresh history (newest first) with reason codes."""
    from app.core.universe.refresh_history_store import RefreshHistoryStore

    store = RefreshHistoryStore()
    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "records": store.read_recent(limit=limit),
    }


@router.get("/data-reliability/events/calendar")
def get_event_calendar(days_ahead: int = Query(default=14, ge=1, le=90)) -> dict:
    """Explicit AVAILABLE / UNAVAILABLE state for macro + earnings calendars."""
    from app.core.data_reliability.event_calendar_status import (
        earnings_calendar_status,
        event_calendar_status,
    )

    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "macro": event_calendar_status(days_ahead).to_dict(),
        "earnings": earnings_calendar_status().to_dict(),
    }
