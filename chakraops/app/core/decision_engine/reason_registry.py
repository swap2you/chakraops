# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Canonical reason-code registry (R36.1 explainability).

Single, additive catalog of the reason codes emitted by the canonical
``decision_engine`` (``gates.py``/``strategies.py``/``engine.py``/``sizing.py``/
``live_service.py`` and the freshness gate). This module does NOT change what
codes are emitted or any decision behavior; it only *describes* the existing
codes so the API/UI can render stable, human-readable explanations.

Design rules:
- Every code has a stable machine ``code``, a ``category`` (gate/stage), a
  ``severity`` (HARD/SOFT/INFO), and a ``klass`` (SAFETY_CRITICAL/TEMPORARY/
  INFORMATIONAL).
- Numeric codes reference the ``measured_field`` and ``threshold_field`` (dotted
  paths into a live item / profile) plus a ``unit`` so a builder can surface
  measured-vs-threshold without re-deriving policy here.
- ``resolve()`` never raises and never leaks raw ``FAIL_``/``WARN_`` text; unknown
  codes map to a safe generic entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Severity of the underlying check.
SEV_HARD = "HARD"   # blocks (BLOCKED status)
SEV_SOFT = "SOFT"   # downgrades to WATCH
SEV_INFO = "INFO"   # informational / positive / provenance

# Explainability class.
KLASS_SAFETY_CRITICAL = "SAFETY_CRITICAL"  # never overridable; must never be a near-miss
KLASS_TEMPORARY = "TEMPORARY"              # may clear on next observation
KLASS_INFORMATIONAL = "INFORMATIONAL"      # not a rejection


@dataclass(frozen=True)
class ReasonCode:
    code: str
    category: str
    severity: str
    klass: str
    title: str
    explanation: str
    strategies: Tuple[str, ...] = ("ALL",)
    measured_field: Optional[str] = None
    threshold_field: Optional[str] = None
    unit: Optional[str] = None
    remediation: Optional[str] = None
    data_source: Optional[str] = None

    @property
    def is_safety_critical(self) -> bool:
        return self.klass == KLASS_SAFETY_CRITICAL

    @property
    def is_temporary(self) -> bool:
        return self.klass == KLASS_TEMPORARY

    def to_dict(self) -> Dict[str, object]:
        return {
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "klass": self.klass,
            "title": self.title,
            "explanation": self.explanation,
            "strategies": list(self.strategies),
            "measured_field": self.measured_field,
            "threshold_field": self.threshold_field,
            "unit": self.unit,
            "remediation": self.remediation,
            "data_source": self.data_source,
        }


def _rc(code, category, severity, klass, title, explanation, **kw) -> ReasonCode:
    return ReasonCode(code=code, category=category, severity=severity, klass=klass,
                      title=title, explanation=explanation, **kw)


# --- Canonical registry (seeded from the verified emission audit) ---------------
_ENTRIES: List[ReasonCode] = [
    # Data freshness / missing critical (hard, safety-critical)
    _rc("STALE_PRICE", "DATA", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Price data is stale", "Underlying price is older than the freshness budget; no advice is issued from stale data.",
        measured_field="data_freshness.PRICE.age_seconds", threshold_field="data_freshness.PRICE.max_age_seconds",
        unit="seconds", remediation="Wait for a fresh ORATS snapshot.", data_source="ORATS"),
    _rc("STALE_OPTIONS_CHAIN", "DATA", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Options chain is stale", "The options chain is older than the freshness budget; advice requires fresh chain data.",
        measured_field="data_freshness.OPTIONS_CHAIN.age_seconds", threshold_field="data_freshness.OPTIONS_CHAIN.max_age_seconds",
        unit="seconds", remediation="Wait for a fresh ORATS chain.", data_source="ORATS"),
    _rc("MISSING_PRICE", "DATA", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Underlying price missing", "No underlying price is available for this symbol.",
        remediation="Confirm ORATS coverage for this symbol.", data_source="ORATS"),
    _rc("MISSING_OPTIONS_CHAIN", "DATA", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Options chain missing", "No options chain is available for this symbol.",
        remediation="Confirm ORATS options coverage.", data_source="ORATS"),
    _rc("MISSING_CONTRACT", "DATA", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "No contract available", "No option contract was available to evaluate for this strategy.",
        data_source="ORATS"),
    _rc("MISSING_STRIKE", "DATA", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Contract strike missing", "The candidate contract has no valid strike.", data_source="ORATS"),
    _rc("MISSING_PREMIUM", "DATA", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Contract premium missing", "The candidate contract has no valid premium.", data_source="ORATS"),
    _rc("MISSING_DELTA", "DATA", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Contract delta missing", "The candidate contract has no delta.", data_source="ORATS"),
    _rc("MISSING_DTE", "DATA", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Contract DTE missing", "The candidate contract has no days-to-expiry.", data_source="ORATS"),

    # Earnings blackout (hard, safety-critical) — family prefix EARNINGS_BLACKOUT_*D
    _rc("EARNINGS_BLACKOUT", "EARNINGS", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Inside earnings blackout", "Earnings fall inside the profile's blackout window; new option risk is blocked.",
        measured_field="event_risk.earnings_days", threshold_field="event_risk.blackout_days",
        unit="days", remediation="Reconsider after the earnings blackout passes.", data_source="ORATS earnings"),

    # Regime (hard, safety-critical) — family prefix REGIME_EXCLUDED_*
    _rc("REGIME_EXCLUDED", "REGIME", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Market regime excluded", "The current market regime is not acceptable for this profile/strategy.",
        remediation="Wait for an acceptable regime for this profile."),

    # Liquidity (hard, safety-critical)
    _rc("LIQUIDITY_DATA_MISSING", "LIQUIDITY", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Liquidity data missing", "Open interest, volume, or spread data was unavailable to validate liquidity.",
        data_source="ORATS"),
    _rc("LOW_OPEN_INTEREST", "LIQUIDITY", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Open interest too low", "Contract open interest is below the profile's minimum.",
        measured_field="selected_contract.open_interest", threshold_field="profile.liquidity.min_open_interest",
        unit="contracts", data_source="ORATS"),
    _rc("LOW_VOLUME", "LIQUIDITY", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Volume too low", "Contract volume is below the profile's minimum.",
        measured_field="selected_contract.volume", threshold_field="profile.liquidity.min_volume",
        unit="contracts", data_source="ORATS"),
    _rc("WIDE_SPREAD", "LIQUIDITY", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Bid/ask spread too wide", "The bid/ask spread exceeds the profile's maximum.",
        measured_field="selected_contract.bid_ask_spread_pct", threshold_field="profile.liquidity.max_bid_ask_spread_pct",
        unit="pct", data_source="ORATS"),

    # Holdings (hard, safety-critical) — covered call coverage
    _rc("INSUFFICIENT_SHARES", "HOLDINGS", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Not enough shares for a covered call", "A covered call requires at least 100 shares held.",
        strategies=("COVERED_CALL",), measured_field="sizing.shares_held", threshold_field="const.100",
        unit="shares", remediation="Acquire at least 100 shares before selling a covered call."),

    # Sector (hard, safety-critical)
    _rc("SECTOR_DATA_UNAVAILABLE", "SECTOR", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Sector data unavailable", "The symbol's sector could not be determined; blocked fail-closed rather than bypassing the cap."),
    _rc("SECTOR_BLOCKED_PENDING_DATA", "SECTOR", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Blocked pending sector data", "Blocked until sector classification is available (fail-closed)."),
    _rc("SECTOR_EXPOSURE_LIMIT_REACHED", "SECTOR", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Sector exposure limit reached", "Adding this position would exceed the profile's sector-exposure cap.",
        threshold_field="profile.max_sector_exposure_pct", unit="pct"),

    # Cash / collateral (hard, safety-critical)
    _rc("INSUFFICIENT_CASH", "CASH", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Insufficient cash for collateral", "Available cash after the buffer is below the collateral for one contract.",
        strategies=("CSP",), remediation="Free up cash or choose a lower-collateral candidate."),
    _rc("CASH_STRATEGIES_BLOCKED_PENDING_CASH_DATA", "CASH", SEV_HARD, KLASS_SAFETY_CRITICAL,
        "Cash strategies blocked pending cash data", "Available cash is unknown, so cash-secured strategies are blocked fail-closed."),

    # Strategy soft gates (WATCH, temporary)
    _rc("DELTA_OUT_OF_RANGE", "DELTA", SEV_SOFT, KLASS_TEMPORARY,
        "Delta outside target range", "The contract's absolute delta is outside the profile's target band.",
        measured_field="selected_contract.delta", threshold_field="profile.delta_range",
        unit="delta", remediation="Look for a strike whose delta is within the band.", data_source="ORATS"),
    _rc("DTE_OUT_OF_RANGE", "DTE", SEV_SOFT, KLASS_TEMPORARY,
        "DTE outside target range", "The contract's days-to-expiry are outside the profile's target range.",
        measured_field="selected_contract.dte", threshold_field="profile.dte_range",
        unit="days", remediation="Look for an expiry within the DTE range.", data_source="ORATS"),
    _rc("BELOW_RETURN_THRESHOLD", "RETURN", SEV_SOFT, KLASS_TEMPORARY,
        "Below return threshold", "The estimated return is below the profile's minimum.",
        measured_field="expected_return_pct", threshold_field="profile.min_return_pct",
        unit="pct", remediation="Consider a higher-premium candidate or wait for better pricing."),
    _rc("ZERO_SIZE", "SIZING", SEV_SOFT, KLASS_TEMPORARY,
        "Sized to zero", "Position sizing resolved to zero contracts/shares under current capital and caps."),
    _rc("UNKNOWN_STRATEGY", "STRATEGY", SEV_SOFT, KLASS_TEMPORARY,
        "Unknown strategy", "The requested strategy is not recognized by the engine."),

    # Sizing informational / temporary flags
    _rc("SECTOR_CAP_ENFORCED", "SIZING", SEV_INFO, KLASS_INFORMATIONAL,
        "Sector cap enforced", "Sizing honored the sector-exposure cap for this symbol's sector."),
    _rc("SECTOR_DATA_UNAVAILABLE_EXISTING_POSITION", "SIZING", SEV_INFO, KLASS_INFORMATIONAL,
        "Sector data unavailable (existing position)", "Sector classification was unavailable while sizing an existing position."),
    _rc("CASH_INSUFFICIENT_FOR_ONE_CONTRACT", "CASH", SEV_SOFT, KLASS_TEMPORARY,
        "Cash insufficient for one contract", "Available cash after the buffer cannot collateralize a single contract.",
        strategies=("CSP",)),
    _rc("INSUFFICIENT_SHARES_FOR_ONE_LOT", "HOLDINGS", SEV_SOFT, KLASS_TEMPORARY,
        "Fewer than 100 shares", "Held shares are below one covered-call lot (100).", strategies=("COVERED_CALL",)),
    _rc("CASH_INSUFFICIENT_FOR_SHARES", "CASH", SEV_SOFT, KLASS_TEMPORARY,
        "Cash insufficient for shares", "Available cash cannot buy a whole-share lot at the current price.",
        strategies=("SHARE_BUY",)),

    # Capital-set safety (live_service)
    _rc("RECOMMENDATION_SET_EXCEEDS_DEPLOYABLE_CAPITAL", "CAPITAL_SET", SEV_SOFT, KLASS_TEMPORARY,
        "Set exceeds deployable capital", "The full recommendation set's required capital exceeds deployable cash; items are sized independently, not jointly."),
    _rc("PER_SUGGESTION_SIZED_INDEPENDENTLY_NOT_JOINTLY_EXECUTABLE", "CAPITAL_SET", SEV_INFO, KLASS_INFORMATIONAL,
        "Sized independently", "Each suggestion is sized on its own; the set is not guaranteed jointly executable."),
    _rc("AVAILABLE_CASH_UNKNOWN", "DATA", SEV_INFO, KLASS_INFORMATIONAL,
        "Available cash unknown", "Cash balance is unknown; cash-secured strategies are treated fail-closed."),

    # Positive / provenance / informational
    _rc("DELTA_IN_RANGE", "DELTA", SEV_INFO, KLASS_INFORMATIONAL,
        "Delta in target range", "The contract's delta is within the profile band.",
        measured_field="selected_contract.delta", threshold_field="profile.delta_range", unit="delta", data_source="ORATS"),
    _rc("DTE_IN_RANGE", "DTE", SEV_INFO, KLASS_INFORMATIONAL,
        "DTE in target range", "The contract's days-to-expiry are within the profile range.",
        measured_field="selected_contract.dte", threshold_field="profile.dte_range", unit="days", data_source="ORATS"),
    _rc("MEETS_RETURN_THRESHOLD", "RETURN", SEV_INFO, KLASS_INFORMATIONAL,
        "Meets return threshold", "Estimated return meets or exceeds the profile minimum.",
        measured_field="expected_return_pct", threshold_field="profile.min_return_pct", unit="pct"),
    _rc("SHARE_BUY_CANDIDATE", "STRATEGY", SEV_INFO, KLASS_INFORMATIONAL,
        "Share-buy candidate", "Evaluated as a share-purchase candidate.", strategies=("SHARE_BUY",)),
    _rc("LIQUIDITY_VALIDATED_UPSTREAM", "LIQUIDITY", SEV_INFO, KLASS_INFORMATIONAL,
        "Liquidity validated upstream", "Option liquidity was validated by the upstream diagnostics pipeline."),
    _rc("EARNINGS_DATA_UNAVAILABLE", "EARNINGS", SEV_INFO, KLASS_INFORMATIONAL,
        "Earnings date unavailable", "No earnings date was available; earnings risk could not be confirmed.", data_source="ORATS earnings"),
    _rc("IV_RANK_UNAVAILABLE", "DATA", SEV_INFO, KLASS_INFORMATIONAL,
        "IV rank unavailable", "IV rank was unavailable for this symbol.", data_source="ORATS"),
    _rc("CASH_IS_FALLBACK_NOT_REQUIRED", "CASH", SEV_INFO, KLASS_INFORMATIONAL,
        "Cash is a fallback", "Stay-in-cash is a valid fallback outcome; actionable candidates also exist."),
    _rc("NO_ACTIONABLE_CANDIDATES", "STRATEGY", SEV_INFO, KLASS_INFORMATIONAL,
        "No actionable candidates", "No candidate met the actionable bar; staying in cash is the outcome."),
]

REGISTRY: Dict[str, ReasonCode] = {e.code: e for e in _ENTRIES}

# Interpolated code families: prefix -> base code in REGISTRY.
_PREFIX_FAMILIES: Tuple[Tuple[str, str], ...] = (
    ("EARNINGS_BLACKOUT_", "EARNINGS_BLACKOUT"),
    ("REGIME_EXCLUDED_", "REGIME_EXCLUDED"),
    ("UNKNOWN_STRATEGY_", "UNKNOWN_STRATEGY"),
)


def _generic(code: str) -> ReasonCode:
    """Safe fallback for unknown codes (never leaks raw FAIL_/WARN_)."""
    return ReasonCode(
        code=code, category="OTHER", severity=SEV_INFO, klass=KLASS_INFORMATIONAL,
        title="Additional reason",
        explanation="See diagnostics for details.",
    )


def resolve(code: Optional[str]) -> ReasonCode:
    """Resolve a raw reason code to a canonical ``ReasonCode`` (never raises)."""
    if not code or not isinstance(code, str):
        return _generic("")
    raw = code.strip()
    # Defensive: strip legacy FAIL_/WARN_ prefixes before matching.
    stripped = raw
    for pref in ("FAIL_", "WARN_"):
        if stripped.startswith(pref):
            stripped = stripped[len(pref):]
    if stripped in REGISTRY:
        return REGISTRY[stripped]
    for prefix, base in _PREFIX_FAMILIES:
        if stripped.startswith(prefix) and base in REGISTRY:
            return REGISTRY[base]
    return _generic(stripped)


def is_safety_critical(code: Optional[str]) -> bool:
    return resolve(code).is_safety_critical


def is_temporary(code: Optional[str]) -> bool:
    return resolve(code).is_temporary


def human_title(code: Optional[str]) -> str:
    return resolve(code).title


def human_explanation(code: Optional[str]) -> str:
    return resolve(code).explanation


def all_codes() -> List[str]:
    return sorted(REGISTRY.keys())
