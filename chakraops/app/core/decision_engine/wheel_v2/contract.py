# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 Wheel V2 contracts — advisory, manual-only, never persist prose to decision artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class OwnabilityResult:
    """Would the operator want shares if assigned? Fail-closed on missing critical inputs."""

    ownable: bool
    reason_codes: List[str] = field(default_factory=list)
    missing_critical: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ownable": self.ownable,
            "reason_codes": list(self.reason_codes),
            "missing_critical": list(self.missing_critical),
        }


@dataclass(frozen=True)
class ManualPlan:
    """Complete manual execution plan (request-time only; not persisted to decision_latest)."""

    strike: Optional[float] = None
    expiry: Optional[str] = None
    dte: Optional[int] = None
    delta: Optional[float] = None
    premium: Optional[float] = None
    breakeven: Optional[float] = None
    collateral: Optional[float] = None
    earnings_days: Optional[int] = None
    profit_target_pct: Optional[float] = None
    roll_dte: Optional[int] = None
    assignment_plan: Optional[str] = None
    thesis_failure_plan: Optional[str] = None
    strategy: Optional[str] = None
    action: Optional[str] = None
    quantity: Optional[int] = None
    staged_tranches: Optional[List[Dict[str, Any]]] = None
    as_of_utc: Optional[str] = None
    sources: List[str] = field(default_factory=list)
    summary_label: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "strike": self.strike,
            "expiry": self.expiry,
            "dte": self.dte,
            "delta": self.delta,
            "premium": self.premium,
            "breakeven": self.breakeven,
            "collateral": self.collateral,
            "earnings_days": self.earnings_days,
            "profit_target_pct": self.profit_target_pct,
            "roll_dte": self.roll_dte,
            "assignment_plan": self.assignment_plan,
            "thesis_failure_plan": self.thesis_failure_plan,
            "strategy": self.strategy,
            "action": self.action,
            "quantity": self.quantity,
            "staged_tranches": list(self.staged_tranches) if self.staged_tranches else None,
            "as_of_utc": self.as_of_utc,
            "sources": list(self.sources),
            "summary_label": self.summary_label,
        }


# Arbitration reason codes (structured; UI uses safe labels).
CSP_PREFERRED = "CSP_PREFERRED"
SHARES_PREFERRED = "SHARES_PREFERRED"
BOTH_UNATTRACTIVE = "BOTH_UNATTRACTIVE"
CASH_INSUFFICIENT = "CASH_INSUFFICIENT"
ASSIGNMENT_INAPPROPRIATE = "ASSIGNMENT_INAPPROPRIATE"

ARBITRATION_LABELS = {
    CSP_PREFERRED: "Cash-secured put preferred",
    SHARES_PREFERRED: "Shares preferred",
    BOTH_UNATTRACTIVE: "Both unattractive — stay in cash",
    CASH_INSUFFICIENT: "Insufficient cash",
    ASSIGNMENT_INAPPROPRIATE: "Assignment inappropriate for ownership",
}


@dataclass(frozen=True)
class ArbitrationResult:
    """CSP vs shares arbitration outcome."""

    winner: str  # CSP | SHARES | CASH | NONE
    loser: Optional[str] = None
    reason_codes: List[str] = field(default_factory=list)
    explanation_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "loser": self.loser,
            "reason_codes": list(self.reason_codes),
            "explanation_codes": list(self.explanation_codes),
            "winner_label": _winner_label(self.winner),
            "reason_labels": [ARBITRATION_LABELS.get(c, "Review") for c in self.reason_codes],
        }


def _winner_label(winner: str) -> str:
    w = (winner or "").upper()
    if w == "CSP":
        return "Cash-secured put"
    if w == "SHARES":
        return "Shares"
    if w == "CASH":
        return "Stay in cash"
    return "No preference"


@dataclass(frozen=True)
class WheelDecisionV2:
    """Full Wheel V2 advisory decision. Always manual_only / trade_execution=false."""

    symbol: str
    phase: str
    action: str
    strategy: Optional[str] = None
    ownability: Optional[Dict[str, Any]] = None
    arbitration: Optional[Dict[str, Any]] = None
    manual_plan: Optional[Dict[str, Any]] = None
    management: Optional[Dict[str, Any]] = None
    assignment: Optional[Dict[str, Any]] = None
    shares_plan: Optional[Dict[str, Any]] = None
    slack_payload: Optional[Dict[str, Any]] = None
    reason_codes: List[str] = field(default_factory=list)
    phase_label: Optional[str] = None
    action_label: Optional[str] = None
    profile: Optional[str] = None
    manual_only: bool = True
    trade_execution: bool = False

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "phase": self.phase,
            "phase_label": self.phase_label,
            "action": self.action,
            "action_label": self.action_label,
            "strategy": self.strategy,
            "ownability": self.ownability,
            "arbitration": self.arbitration,
            "manual_plan": self.manual_plan,
            "management": self.management,
            "assignment": self.assignment,
            "shares_plan": self.shares_plan,
            "slack_payload": self.slack_payload,
            "reason_codes": list(self.reason_codes),
            "profile": self.profile,
            "manual_only": True,
            "trade_execution": False,
        }
