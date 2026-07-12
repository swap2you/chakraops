# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe V2 (R36.2) policy — pure, deterministic derivation. No I/O.

Derives lifecycle state and independent per-strategy membership from a normalized
per-symbol evaluation outcome, reusing the R36.1 canonical reason registry and the
inherited strategy profiles / universe gate config. This module changes NO threshold
and calls NO provider.

See docs/ai/releases/R36.2/{R36_2_LIFECYCLE_SPEC,R36_2_MEMBERSHIP_SPEC}.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.decision_engine import reason_registry
from app.core.universe_v2.model import (
    LIFECYCLE_ADMITTED,
    LIFECYCLE_QUARANTINE,
    LIFECYCLE_REMOVED,
    LIFECYCLE_WATCH,
    MEMBERSHIP_ELIGIBLE,
    MEMBERSHIP_NOT_ELIGIBLE,
    MEMBERSHIP_NOT_EVALUATED,
    STRATEGY_AGGRESSIVE_WHEEL,
    STRATEGY_BALANCED_WHEEL,
    STRATEGY_CORE_WHEEL,
    STRATEGY_SHARES,
    StrategyMembership,
)

# Wheel strategy -> inherited profile name (no tuning; profiles are the source of truth).
WHEEL_PROFILE = {
    STRATEGY_CORE_WHEEL: "conservative",
    STRATEGY_BALANCED_WHEEL: "balanced",
    STRATEGY_AGGRESSIVE_WHEEL: "aggressive",
}

# Naming alias between the market-regime vocabulary (RISK_ON/NEUTRAL/RISK_OFF and the
# IV-band HIGH_VOL) and the canonical profile-regime vocabulary the decision engine gates on
# (BULL/NEUTRAL/BEAR/VOLATILE — see decision_engine.profiles.KNOWN_REGIMES and
# decision_engine.gates.regime_gate). This is a translation alias only; it introduces no
# threshold and no new policy value. Any regime token NOT present here is treated as
# UNKNOWN and is fail-closed (never grants wheel eligibility).
REGIME_ALIAS = {
    "RISK_ON": "BULL",
    "BULL": "BULL",
    "NEUTRAL": "NEUTRAL",
    "RISK_OFF": "BEAR",
    "BEAR": "BEAR",
    "VOLATILE": "VOLATILE",
    "HIGH_VOL": "VOLATILE",
}

# Universe-native reason descriptors (NOT decision-engine codes; the registry is not
# modified). Shaped like ``ReasonCode.to_dict()`` so the UI renders them identically.
_UNIVERSE_REASONS: Dict[str, Dict[str, Any]] = {
    "MANUAL_REMOVED": {
        "code": "MANUAL_REMOVED", "category": "LIFECYCLE",
        "severity": reason_registry.SEV_INFO, "klass": reason_registry.KLASS_INFORMATIONAL,
        "title": "Manually removed", "explanation": "The symbol was explicitly removed from the universe by an operator.",
    },
    "NOT_EVALUATED": {
        "code": "NOT_EVALUATED", "category": "LIFECYCLE",
        "severity": reason_registry.SEV_INFO, "klass": reason_registry.KLASS_INFORMATIONAL,
        "title": "Not evaluated yet", "explanation": "No completed evaluation exists for this symbol; eligibility is unknown (fail-closed).",
    },
    "ADMITTED_QUALITY_PASS": {
        "code": "ADMITTED_QUALITY_PASS", "category": "LIFECYCLE",
        "severity": reason_registry.SEV_INFO, "klass": reason_registry.KLASS_INFORMATIONAL,
        "title": "Passed universe quality", "explanation": "The symbol passed the universe quality checks with fresh data.",
    },
    "UNDER_OBSERVATION": {
        "code": "UNDER_OBSERVATION", "category": "LIFECYCLE",
        "severity": reason_registry.SEV_SOFT, "klass": reason_registry.KLASS_TEMPORARY,
        "title": "Under observation", "explanation": "The symbol is being observed after a temporary or soft check outcome.",
    },
    "REGIME_NOT_ACCEPTABLE": {
        "code": "REGIME_NOT_ACCEPTABLE", "category": "REGIME",
        "severity": reason_registry.SEV_SOFT, "klass": reason_registry.KLASS_TEMPORARY,
        "title": "Regime not acceptable for profile", "explanation": "The current market regime is not in this profile's acceptable set.",
        "unit": "regime",
    },
    "SHARE_NOT_ADMISSIBLE": {
        "code": "SHARE_NOT_ADMISSIBLE", "category": "SHARES",
        "severity": reason_registry.SEV_SOFT, "klass": reason_registry.KLASS_TEMPORARY,
        "title": "Not admissible for shares", "explanation": "The symbol's price/quality does not meet the share-admissibility bounds.",
        "unit": "usd",
    },
    "QUALITY_FAILED": {
        "code": "QUALITY_FAILED", "category": "QUALITY",
        "severity": reason_registry.SEV_SOFT, "klass": reason_registry.KLASS_TEMPORARY,
        "title": "Universe quality not met", "explanation": "The symbol did not pass the universe quality checks.",
    },
    "DATA_INCOMPLETE": {
        "code": "DATA_INCOMPLETE", "category": "DATA",
        "severity": reason_registry.SEV_SOFT, "klass": reason_registry.KLASS_TEMPORARY,
        "title": "Data incomplete", "explanation": "Provider data completeness is below the required threshold; eligibility is withheld (fail-closed).",
    },
    "NOT_FRESH": {
        "code": "NOT_FRESH", "category": "DATA",
        "severity": reason_registry.SEV_HARD, "klass": reason_registry.KLASS_SAFETY_CRITICAL,
        "title": "Data not fresh", "explanation": "Provider data is not fresh enough to determine eligibility (fail-closed).",
    },
}


def resolve_reason(code: Optional[str]) -> Dict[str, Any]:
    """Resolve a code to a UI-safe reason dict. Universe-native codes first, then the
    canonical R36.1 registry (which never leaks raw FAIL_/WARN_)."""
    if code and code in _UNIVERSE_REASONS:
        return dict(_UNIVERSE_REASONS[code])
    return reason_registry.resolve(code).to_dict()


def reason_is_safety_critical(reason: Dict[str, Any]) -> bool:
    return bool(reason) and reason.get("klass") == reason_registry.KLASS_SAFETY_CRITICAL


@dataclass
class SymbolEvalOutcome:
    """Normalized per-symbol inputs (built from the latest evaluation artifact)."""

    symbol: str
    has_evaluation: bool = False
    is_removed: bool = False  # manual/static removal
    reason_codes: Tuple[str, ...] = ()
    stage1_pass: bool = False
    verdict: Optional[str] = None  # ELIGIBLE|HOLD|BLOCKED|NOT_EVALUATED
    provider_ok: bool = True  # False only on a hard provider ERROR (safety-critical quarantine)
    data_complete: bool = True  # False when provider_status is WARN/None (incomplete data → fail-closed, not admitted)
    regime: Optional[str] = None
    price: Optional[float] = None
    evaluation_version: Optional[str] = None
    as_of_utc: Optional[str] = None


def _first_safety_critical(reason_codes: Tuple[str, ...]) -> Optional[str]:
    for c in reason_codes:
        if reason_registry.is_safety_critical(c):
            return c
    return None


def _first_temporary(reason_codes: Tuple[str, ...]) -> Optional[str]:
    for c in reason_codes:
        if reason_registry.is_temporary(c):
            return c
    return None


def _share_price_bounds() -> Tuple[float, Optional[float]]:
    from app.core.config.universe_gates_config import get_gate_config

    cfg = get_gate_config()
    lo = float(cfg.get("min_price_usd") or 0.0)
    hi = cfg.get("max_price_usd")
    hi_val = float(hi) if hi and float(hi) > 0 else None
    return lo, hi_val


def _acceptable_regimes(strategy: str) -> List[str]:
    """Inherited acceptable regimes for a wheel strategy's profile (no tuning)."""
    profile_name = WHEEL_PROFILE.get(strategy)
    if not profile_name:
        return []
    try:
        from app.core.decision_engine.profiles import get_profile

        return list(get_profile(profile_name).acceptable_regimes)
    except Exception:
        return []


def mapped_regime(regime: Optional[str]) -> Optional[str]:
    """Translate a raw regime token to the canonical profile vocabulary, or None if unknown."""
    if not regime:
        return None
    return REGIME_ALIAS.get(regime.strip().upper())


def _strategy_admits(strategy: str, outcome: SymbolEvalOutcome) -> bool:
    """Pure strategy-specific admissibility predicate, assuming the symbol already passed
    universe quality with fresh/complete data. Shares: price within the inherited quality
    band. Wheels: fail-closed — admit ONLY when the current regime maps to a regime the
    profile accepts (mirrors decision_engine.gates.regime_gate, which requires the regime to
    be IN acceptable_regimes). An unknown/missing regime never grants wheel eligibility."""
    if strategy == STRATEGY_SHARES:
        lo, hi = _share_price_bounds()
        price = outcome.price
        return price is not None and price >= lo and (hi is None or price <= hi)

    acceptable = _acceptable_regimes(strategy)
    mr = mapped_regime(outcome.regime)
    return bool(acceptable) and mr is not None and mr in acceptable


def _quality_admissible(outcome: SymbolEvalOutcome) -> bool:
    """True when the symbol passed universe quality with fresh/complete data and no
    safety-critical/temporary/blocking outcome. This is the ADMITTED precondition (before
    the ≥1-strategy check)."""
    if not outcome.has_evaluation or outcome.is_removed:
        return False
    if not outcome.provider_ok or not outcome.data_complete:
        return False
    if _first_safety_critical(outcome.reason_codes) is not None:
        return False
    if _first_temporary(outcome.reason_codes) is not None:
        return False
    if (outcome.verdict or "").strip().upper() == "BLOCKED":
        return False
    return bool(outcome.stage1_pass)


def derive_lifecycle(outcome: SymbolEvalOutcome) -> Tuple[str, str, bool, bool]:
    """Return (lifecycle_state, primary_reason_code, safety_critical, temporary).

    Precedence (per R36_2_LIFECYCLE_SPEC): REMOVED (manual/static) → QUARANTINE
    (safety-critical) → ADMITTED (quality-passed AND eligible for ≥1 strategy) → WATCH.
    """
    if outcome.is_removed:
        return LIFECYCLE_REMOVED, "MANUAL_REMOVED", False, False

    sc_code = _first_safety_critical(outcome.reason_codes)
    if sc_code is not None or not outcome.provider_ok:
        return LIFECYCLE_QUARANTINE, (sc_code or "NOT_FRESH"), True, False

    if not outcome.has_evaluation:
        return LIFECYCLE_WATCH, "NOT_EVALUATED", False, False

    temporary_code = _first_temporary(outcome.reason_codes)
    temporary = temporary_code is not None

    if _quality_admissible(outcome):
        # ADMITTED only if the symbol qualifies for at least one strategy universe.
        from app.core.universe_v2.model import ALL_STRATEGIES

        if any(_strategy_admits(s, outcome) for s in ALL_STRATEGIES):
            return LIFECYCLE_ADMITTED, "ADMITTED_QUALITY_PASS", False, False
        # Quality-passed but no strategy currently accepts (e.g. regime) → WATCH.
        return LIFECYCLE_WATCH, "REGIME_NOT_ACCEPTABLE", False, False

    # Not quality-admissible: pick the most informative soft/withheld reason (never quarantine).
    if not outcome.data_complete:
        return LIFECYCLE_WATCH, "DATA_INCOMPLETE", False, False
    if temporary:
        return LIFECYCLE_WATCH, temporary_code, False, True
    blocked = (outcome.verdict or "").strip().upper() == "BLOCKED"
    if not outcome.stage1_pass or blocked:
        return LIFECYCLE_WATCH, "QUALITY_FAILED", False, False
    return LIFECYCLE_WATCH, "UNDER_OBSERVATION", False, False


def derive_membership(
    strategy: str,
    outcome: SymbolEvalOutcome,
    lifecycle_state: str,
    safety_critical: bool,
) -> StrategyMembership:
    """Derive independent membership for one strategy (symbol-level admissibility)."""
    m = StrategyMembership(strategy=strategy, status=MEMBERSHIP_NOT_EVALUATED)

    if not outcome.has_evaluation:
        m.status = MEMBERSHIP_NOT_EVALUATED
        m.primary_reason = resolve_reason("NOT_EVALUATED")
        return m

    if lifecycle_state in (LIFECYCLE_QUARANTINE, LIFECYCLE_REMOVED) or safety_critical or not outcome.provider_ok:
        m.status = MEMBERSHIP_NOT_ELIGIBLE
        sc = _first_safety_critical(outcome.reason_codes)
        if lifecycle_state == LIFECYCLE_REMOVED:
            m.primary_reason = resolve_reason("MANUAL_REMOVED")
        elif sc:
            m.primary_reason = resolve_reason(sc)
        else:
            m.primary_reason = resolve_reason("NOT_FRESH")
        return m

    # Fail-closed: incomplete provider data (WARN) can never yield an eligible membership.
    if not outcome.data_complete:
        m.status = MEMBERSHIP_NOT_ELIGIBLE
        m.primary_reason = resolve_reason("DATA_INCOMPLETE")
        return m

    if not outcome.stage1_pass:
        m.status = MEMBERSHIP_NOT_ELIGIBLE
        m.primary_reason = resolve_reason("QUALITY_FAILED")
        return m

    # Strategy-specific admissibility (regime for wheels, price band for shares).
    if strategy == STRATEGY_SHARES:
        lo, hi = _share_price_bounds()
        price = outcome.price
        if not _strategy_admits(strategy, outcome):
            m.status = MEMBERSHIP_NOT_ELIGIBLE
            m.primary_reason = resolve_reason("SHARE_NOT_ADMISSIBLE")
            m.measured = price
            m.threshold = [lo, hi] if hi is not None else lo
            m.unit = "usd"
            return m
    else:
        acceptable = _acceptable_regimes(strategy)
        if not _strategy_admits(strategy, outcome):
            m.status = MEMBERSHIP_NOT_ELIGIBLE
            m.primary_reason = resolve_reason("REGIME_NOT_ACCEPTABLE")
            m.threshold = acceptable
            m.unit = "regime"
            return m

    # Strategy accepts the symbol. Per spec rule 3, ELIGIBLE additionally requires the
    # symbol to be ADMITTED (fresh, quality-passed, not temporarily under observation).
    if lifecycle_state != LIFECYCLE_ADMITTED:
        m.status = MEMBERSHIP_NOT_ELIGIBLE
        m.primary_reason = resolve_reason("UNDER_OBSERVATION")
        return m

    m.status = MEMBERSHIP_ELIGIBLE
    m.primary_reason = resolve_reason("ADMITTED_QUALITY_PASS")
    if strategy != STRATEGY_SHARES:
        acceptable = _acceptable_regimes(strategy)
        if acceptable:
            m.threshold = acceptable
            m.unit = "regime"
    return m


def derive_memberships(
    outcome: SymbolEvalOutcome,
    lifecycle_state: str,
    safety_critical: bool,
) -> Dict[str, StrategyMembership]:
    from app.core.universe_v2.model import ALL_STRATEGIES

    return {
        s: derive_membership(s, outcome, lifecycle_state, safety_critical)
        for s in ALL_STRATEGIES
    }
