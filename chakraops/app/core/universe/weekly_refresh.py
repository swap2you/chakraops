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
OUTCOME_DRY_RUN = "DRY_RUN"

# Transaction name shared by the cross-process lock + journal.
_TXN_NAME = "weekly_refresh"


class WeeklyRefreshError(RuntimeError):
    """Raised when an operational refresh fails to apply or record atomically.

    Recoverable: the overlay was rolled back to its pre-transaction snapshot, so
    the universe is left in a consistent (pre-refresh) state.
    """


class WeeklyRefreshCriticalError(WeeklyRefreshError):
    """Rollback or recovery itself failed; the system may be inconsistent.

    The transaction journal is intentionally preserved as evidence and to allow
    a subsequent run to attempt deterministic recovery. Requires operator
    attention — never silently swallowed.
    """


def _recover_pending_transaction(store: Any, *, restore_overlay: Any) -> Optional[Dict[str, Any]]:
    """Reconcile an interrupted transaction from the journal (caller holds lock).

    Determinism rule: the history append is the single commit point.
    * If the history already contains a record for the journaled week, the
      transaction had effectively committed -> clear the journal.
    * Otherwise the overlay may be partially applied -> roll it back to the
      pre-transaction snapshot recorded in the journal, then clear the journal.
    A failed rollback raises :class:`WeeklyRefreshCriticalError` and preserves
    the journal as evidence.
    """
    from app.core.universe.refresh_lock import clear_journal, journal_path, read_journal

    journal = read_journal(_TXN_NAME)
    if not journal:
        return None
    week = journal.get("week_id")
    prev_overlay = journal.get("prev_overlay") or {"added": [], "removed": []}
    last = store.last()
    if last and last.get("week_id") == week:
        clear_journal(_TXN_NAME)
        return {"recovered": "COMMITTED", "week_id": week}
    try:
        restore_overlay(prev_overlay)
    except Exception as e:
        raise WeeklyRefreshCriticalError(
            f"weekly refresh recovery rollback failed for week {week}; journal "
            f"preserved at {journal_path(_TXN_NAME)}: {e}"
        ) from e
    clear_journal(_TXN_NAME)
    return {"recovered": "ROLLED_BACK", "week_id": week}


def recover_pending_transaction(history_store: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Public, lock-guarded recovery of an interrupted refresh transaction.

    Safe to call at admin-route entry or startup. Returns ``None`` when there is
    nothing to recover.
    """
    from app.core.universe.refresh_history_store import RefreshHistoryStore
    from app.core.universe.refresh_lock import cross_process_lock
    from app.core.universe.universe_overrides import restore_overlay

    store = history_store or RefreshHistoryStore()
    with cross_process_lock(_TXN_NAME):
        return _recover_pending_transaction(store, restore_overlay=restore_overlay)


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

    Transaction-safe pipeline, executed under a single cross-process lock that
    covers the whole unit of work (recovery -> idempotency check -> snapshot ->
    overlay update -> history update -> completion):

    1. Recover any prior interrupted transaction from the journal.
    2. Idempotency: skip if a record for this ISO week already exists.
    3. Snapshot the overlay and write a transaction journal *before* mutating.
    4. Apply the deterministic universe to the canonical overlay (atomic write).
    5. Append exactly one history record (atomic write) — the commit point.
    6. Clear the journal.

    If the overlay apply or the history append fails, the overlay is rolled back
    to the pre-transaction snapshot. A failed rollback raises
    :class:`WeeklyRefreshCriticalError` and preserves the journal as evidence —
    it is never ignored. Concurrent same-week callers produce exactly one applied
    refresh and one history record; the rest observe ``SKIPPED_IDEMPOTENT``.

    Does NOT run automatically; R35 owns scheduling. Intended for a controlled
    manual/admin trigger.
    """
    from app.core.universe.refresh_history_store import RefreshHistoryStore
    from app.core.universe.refresh_lock import (
        clear_journal,
        cross_process_lock,
        journal_path,
        write_journal,
    )
    from app.core.universe.universe_overrides import (
        apply_effective_universe,
        restore_overlay,
        snapshot_overlay,
    )

    as_of = as_of or datetime.now(timezone.utc).date()
    store = history_store or RefreshHistoryStore()
    week = iso_week_id(as_of)

    with cross_process_lock(_TXN_NAME):
        # (1) Reconcile any interrupted prior transaction first.
        _recover_pending_transaction(store, restore_overlay=restore_overlay)

        # (2) Idempotency check (inside the lock so it is race-free).
        last = store.last()
        if last and last.get("week_id") == week:
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
                "outcome": OUTCOME_DRY_RUN,
                "week_id": result.week_id,
                "result": result.to_dict(),
                "applied_added": [],
                "applied_removed": [],
                "record": None,
            }

        # (3) Snapshot + journal BEFORE any mutation, so recovery can roll back.
        prev_overlay = snapshot_overlay()
        journal_payload = {
            "week_id": result.week_id,
            "phase": "apply",
            "prev_overlay": {
                "added": list(prev_overlay.get("added") or []),
                "removed": list(prev_overlay.get("removed") or []),
            },
            "target_symbols": list(result.symbols),
            "source": source,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        write_journal(_TXN_NAME, journal_payload)

        # (4) Apply the overlay (atomic). Roll back on any failure.
        try:
            applied_added, applied_removed = apply_effective_universe(result.symbols, base_symbols)
        except Exception as e:
            try:
                restore_overlay(prev_overlay)
            except Exception as re:
                raise WeeklyRefreshCriticalError(
                    f"weekly refresh apply failed AND overlay rollback failed; "
                    f"journal preserved at {journal_path(_TXN_NAME)}: "
                    f"apply={e}; rollback={re}"
                ) from re
            clear_journal(_TXN_NAME)
            raise WeeklyRefreshError(f"weekly refresh apply failed: {e}") from e

        # (5) Commit: append exactly one history record (atomic).
        journal_payload["phase"] = "history"
        write_journal(_TXN_NAME, journal_payload)
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
            try:
                restore_overlay(prev_overlay)
            except Exception as re:
                # Rollback failure is NEVER ignored: raise critical + keep journal.
                raise WeeklyRefreshCriticalError(
                    f"weekly refresh history append failed AND overlay rollback "
                    f"failed; journal preserved at {journal_path(_TXN_NAME)}: "
                    f"append={e}; rollback={re}"
                ) from re
            clear_journal(_TXN_NAME)
            raise WeeklyRefreshError(
                f"weekly refresh history append failed (overlay rolled back): {e}"
            ) from e

        # (6) Completion.
        clear_journal(_TXN_NAME)
        return {
            "outcome": OUTCOME_APPLIED,
            "week_id": result.week_id,
            "result": result.to_dict(),
            "applied_added": applied_added,
            "applied_removed": applied_removed,
            "record": record,
        }
