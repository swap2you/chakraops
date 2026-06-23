# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Data freshness timestamps and stale-data blocking gate (R32.0).

Pure, deterministic helpers. No network, no I/O, no secrets.

Design intent
-------------
ChakraOps must never produce an actionable recommendation from stale or
missing critical data, and must never silently fall back to an alternate
provider. These helpers make freshness an explicit, testable property:

- ``evaluate_freshness`` classifies a single data input as FRESH / STALE /
  MISSING relative to a max age.
- ``stale_data_gate`` aggregates per-input results and decides whether a
  decision must be blocked, returning machine-readable reason codes.

Reason codes are code-only labels (e.g. ``STALE_OPTIONS_CHAIN``). UI-facing
layers map them to prose; they are never raw FAIL_/WARN_/PASS labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional

FRESH = "FRESH"
STALE = "STALE"
MISSING = "MISSING"

VALID_STATUSES = frozenset({FRESH, STALE, MISSING})


def _as_aware_utc(dt: datetime) -> datetime:
    """Return ``dt`` as a timezone-aware UTC datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class FreshnessResult:
    """Freshness classification for a single named data input."""

    label: str
    status: str
    as_of_utc: Optional[str]
    age_seconds: Optional[float]
    max_age_seconds: float
    required: bool

    @property
    def is_blocking(self) -> bool:
        """True when this input must block an actionable recommendation."""
        return self.required and self.status in (STALE, MISSING)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "status": self.status,
            "as_of_utc": self.as_of_utc,
            "age_seconds": self.age_seconds,
            "max_age_seconds": self.max_age_seconds,
            "required": self.required,
            "is_blocking": self.is_blocking,
        }


def evaluate_freshness(
    label: str,
    as_of: Optional[datetime],
    *,
    max_age_seconds: float,
    now: Optional[datetime] = None,
    required: bool = True,
) -> FreshnessResult:
    """Classify one data input's freshness.

    Parameters
    ----------
    label:
        Stable code-only identifier for the input (e.g. ``OPTIONS_CHAIN``).
    as_of:
        Timestamp the data was produced/observed. ``None`` => MISSING.
    max_age_seconds:
        Maximum allowed age before the data is considered STALE. Must be > 0.
    now:
        Reference time (defaults to ``datetime.now(timezone.utc)``). Injected
        in tests for determinism.
    required:
        When True, STALE/MISSING blocks actionable recommendations.
    """
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")

    if as_of is None:
        return FreshnessResult(
            label=label,
            status=MISSING,
            as_of_utc=None,
            age_seconds=None,
            max_age_seconds=float(max_age_seconds),
            required=required,
        )

    now_utc = _as_aware_utc(now or datetime.now(timezone.utc))
    as_of_utc = _as_aware_utc(as_of)
    age = (now_utc - as_of_utc).total_seconds()
    status = STALE if age > max_age_seconds else FRESH
    return FreshnessResult(
        label=label,
        status=status,
        as_of_utc=as_of_utc.isoformat(),
        age_seconds=age,
        max_age_seconds=float(max_age_seconds),
        required=required,
    )


@dataclass(frozen=True)
class StaleDataGateResult:
    """Aggregate decision over multiple freshness results."""

    blocked: bool
    reason_codes: List[str] = field(default_factory=list)
    results: List[FreshnessResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "blocked": self.blocked,
            "reason_codes": list(self.reason_codes),
            "inputs": [r.to_dict() for r in self.results],
        }


def stale_data_gate(results: Iterable[FreshnessResult]) -> StaleDataGateResult:
    """Block actionable output when any required input is STALE or MISSING.

    Returns a deterministic result with sorted reason codes of the form
    ``STALE_<LABEL>`` / ``MISSING_<LABEL>``. This is the single enforcement
    point for "no actionable recommendation from stale or missing critical
    data" — there is no provider fallback path.
    """
    materialized = list(results)
    reasons: List[str] = []
    for r in materialized:
        if r.is_blocking:
            reasons.append(f"{r.status}_{r.label}")
    reasons.sort()
    return StaleDataGateResult(
        blocked=bool(reasons),
        reason_codes=reasons,
        results=materialized,
    )
