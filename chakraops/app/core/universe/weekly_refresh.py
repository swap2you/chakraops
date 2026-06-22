# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Deterministic weekly universe refresh (R32.0).

Given a universe manifest and a reference date, compute the active weekly
universe deterministically: identical inputs always produce identical output
(sorted, de-duplicated, overrides applied). The refresh also emits stable
reason codes describing how the universe changed versus the previous run, so
the change is auditable.

Pure and deterministic: no network, no time-of-day dependence beyond the
supplied ``as_of`` date. Persistence of run history lives in
``refresh_history_store``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Reason codes (code-only labels).
INITIAL = "INITIAL"
UNCHANGED = "UNCHANGED"
ADDED = "ADDED"
REMOVED_NOT_IN_MANIFEST = "REMOVED_NOT_IN_MANIFEST"
REMOVED_OVERRIDE_DISABLED = "REMOVED_OVERRIDE_DISABLED"


def iso_week_id(d: date) -> str:
    """Return a stable ISO year-week identifier, e.g. ``2026-W25``."""
    iso = d.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def weekly_refresh_due(last_refresh: Optional[date], now: date) -> bool:
    """Return True when a weekly refresh is due.

    Due when there is no prior refresh, when the ISO week differs, or when at
    least 7 days have elapsed (whichever applies). Deterministic for a given
    pair of dates.
    """
    if last_refresh is None:
        return True
    if iso_week_id(last_refresh) != iso_week_id(now):
        return True
    return (now - last_refresh) >= timedelta(days=7)


def _enabled_symbols(manifest: Dict[str, Any]) -> List[str]:
    """Collect enabled, de-duplicated, normalized symbols from the manifest.

    Mirrors ``universe_manager`` semantics: skip disabled tiers, drop symbols
    disabled via ``symbol_overrides``. Returns a sorted, deterministic list.
    """
    overrides = manifest.get("symbol_overrides") or {}
    out: set[str] = set()
    for tier in manifest.get("tiers") or []:
        if not isinstance(tier, dict):
            continue
        if not tier.get("enabled", True):
            continue
        for raw in tier.get("symbols") or []:
            s = (raw or "").strip().upper()
            if not s:
                continue
            ov = overrides.get(s) if isinstance(overrides.get(s), dict) else None
            if ov is not None and ov.get("enabled") is False:
                continue
            out.add(s)
    return sorted(out)


def _disabled_by_override(manifest: Dict[str, Any]) -> set[str]:
    overrides = manifest.get("symbol_overrides") or {}
    disabled: set[str] = set()
    for sym, ov in overrides.items():
        if isinstance(ov, dict) and ov.get("enabled") is False:
            disabled.add((sym or "").strip().upper())
    return disabled


@dataclass(frozen=True)
class WeeklyUniverseResult:
    week_id: str
    as_of: str
    symbols: List[str]
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "week_id": self.week_id,
            "as_of": self.as_of,
            "symbols": list(self.symbols),
            "added": list(self.added),
            "removed": list(self.removed),
            "reason_codes": list(self.reason_codes),
            "count": len(self.symbols),
        }


def compute_weekly_universe(
    manifest: Dict[str, Any],
    as_of: date,
    previous_symbols: Optional[List[str]] = None,
) -> WeeklyUniverseResult:
    """Deterministically compute the weekly universe and change reasons.

    Parameters
    ----------
    manifest:
        Universe manifest (same shape as ``universe_manager`` consumes).
    as_of:
        Reference date for the week id.
    previous_symbols:
        Symbols from the prior refresh, used to derive change reason codes.
        ``None`` => first run (INITIAL).
    """
    symbols = _enabled_symbols(manifest)
    week = iso_week_id(as_of)

    if previous_symbols is None:
        return WeeklyUniverseResult(
            week_id=week,
            as_of=as_of.isoformat(),
            symbols=symbols,
            added=list(symbols),
            removed=[],
            reason_codes=[INITIAL],
        )

    prev = sorted({(s or "").strip().upper() for s in previous_symbols if (s or "").strip()})
    prev_set = set(prev)
    cur_set = set(symbols)
    added = sorted(cur_set - prev_set)
    removed = sorted(prev_set - cur_set)

    reasons: List[str] = []
    if added:
        reasons.append(ADDED)
    if removed:
        disabled = _disabled_by_override(manifest)
        if any(r in disabled for r in removed):
            reasons.append(REMOVED_OVERRIDE_DISABLED)
        if any(r not in disabled for r in removed):
            reasons.append(REMOVED_NOT_IN_MANIFEST)
    if not reasons:
        reasons.append(UNCHANGED)

    return WeeklyUniverseResult(
        week_id=week,
        as_of=as_of.isoformat(),
        symbols=symbols,
        added=added,
        removed=removed,
        reason_codes=reasons,
    )


# Outcome codes (code-only labels) for the operational refresh.
OUTCOME_APPLIED = "APPLIED"
OUTCOME_SKIPPED_IDEMPOTENT = "SKIPPED_IDEMPOTENT"


class WeeklyRefreshError(RuntimeError):
    """Raised when an operational refresh fails to apply or record atomically."""


def apply_weekly_universe_refresh(
    *,
    as_of: Optional[date] = None,
    manifest: Optional[Dict[str, Any]] = None,
    base_symbols: Optional[List[str]] = None,
    history_store: Optional[Any] = None,
    source: str = "weekly_refresh",
    run_at: Optional[datetime] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Operationally apply the deterministic weekly universe (R34.0).

    Pipeline: compute -> idempotency check (week id) -> apply to the canonical
    overlay store -> append exactly one history record. The apply and the record
    are coupled atomically: if the history append fails the applied overlay is
    rolled back, so a partially-applied universe is never left behind.

    Does NOT run automatically; R35 owns scheduling. Intended for a controlled
    manual/admin trigger.

    Parameters
    ----------
    as_of: reference date (defaults to today, UTC).
    manifest: universe manifest (defaults to the configured manifest).
    base_symbols: CSV base universe (defaults to the canonical base).
    history_store: ``RefreshHistoryStore`` (defaults to the canonical store).
    dry_run: compute + diff only; never mutates the overlay or history.
    """
    from app.core.universe.refresh_history_store import RefreshHistoryStore
    from app.core.universe.universe_overrides import (
        apply_effective_universe,
        restore_overlay,
        snapshot_overlay,
    )

    as_of = as_of or datetime.now(timezone.utc).date()
    store = history_store or RefreshHistoryStore()
    week = iso_week_id(as_of)

    last = store.last()
    if last and last.get("week_id") == week:
        # Idempotent: a record for this ISO week already exists. Do not re-apply
        # and do not append a duplicate weekly record.
        return {
            "outcome": OUTCOME_SKIPPED_IDEMPOTENT,
            "week_id": week,
            "reason_codes": ["ALREADY_REFRESHED_THIS_WEEK"],
            "record": last,
            "applied_added": [],
            "applied_removed": [],
        }

    if manifest is None:
        from app.core.universe.universe_manager import load_universe_manifest

        manifest = load_universe_manifest()
    if base_symbols is None:
        from app.api.data_health import get_base_universe_symbols

        base_symbols = get_base_universe_symbols()

    previous_symbols = list(last.get("symbols")) if last else None
    result = compute_weekly_universe(manifest, as_of, previous_symbols=previous_symbols)

    if dry_run:
        return {
            "outcome": "DRY_RUN",
            "week_id": result.week_id,
            "result": result.to_dict(),
            "applied_added": [],
            "applied_removed": [],
            "record": None,
        }

    prev_overlay = snapshot_overlay()
    try:
        applied_added, applied_removed = apply_effective_universe(result.symbols, base_symbols)
    except Exception as e:  # fail-loud; nothing recorded
        raise WeeklyRefreshError(f"weekly refresh apply failed: {e}") from e

    try:
        record = store.append(
            week_id=result.week_id,
            symbols=result.symbols,
            reason_codes=result.reason_codes,
            added=result.added,
            removed=result.removed,
            source=source,
            run_at=run_at,
        )
    except Exception as e:
        # Roll back the applied overlay so the universe is never partially applied.
        try:
            restore_overlay(prev_overlay)
        except Exception:
            pass
        raise WeeklyRefreshError(
            f"weekly refresh history append failed (overlay rolled back): {e}"
        ) from e

    return {
        "outcome": OUTCOME_APPLIED,
        "week_id": result.week_id,
        "result": result.to_dict(),
        "applied_added": applied_added,
        "applied_removed": applied_removed,
        "record": record,
    }
