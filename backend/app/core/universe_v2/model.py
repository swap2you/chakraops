# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe V2 (R36.2) data model — pure dataclasses, no I/O.

See docs/ai/releases/R36.2/R36_2_DATA_MODEL.md for the authoritative spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

SCHEMA_VERSION = "univ2.v1"

# Lifecycle states (symbol-level).
LIFECYCLE_ADMITTED = "ADMITTED"
LIFECYCLE_WATCH = "WATCH"
LIFECYCLE_QUARANTINE = "QUARANTINE"
LIFECYCLE_REMOVED = "REMOVED"
ALL_LIFECYCLE_STATES = (
    LIFECYCLE_ADMITTED,
    LIFECYCLE_WATCH,
    LIFECYCLE_QUARANTINE,
    LIFECYCLE_REMOVED,
)

# Strategy universes (independent memberships).
STRATEGY_CORE_WHEEL = "CORE_WHEEL"
STRATEGY_BALANCED_WHEEL = "BALANCED_WHEEL"
STRATEGY_AGGRESSIVE_WHEEL = "AGGRESSIVE_WHEEL"
STRATEGY_SHARES = "SHARES"
ALL_STRATEGIES = (
    STRATEGY_CORE_WHEEL,
    STRATEGY_BALANCED_WHEEL,
    STRATEGY_AGGRESSIVE_WHEEL,
    STRATEGY_SHARES,
)

# Membership status.
MEMBERSHIP_ELIGIBLE = "ELIGIBLE"
MEMBERSHIP_NOT_ELIGIBLE = "NOT_ELIGIBLE"
MEMBERSHIP_NOT_EVALUATED = "NOT_EVALUATED"

# Snapshot status.
SNAPSHOT_COMPLETE = "COMPLETE"
SNAPSHOT_STALE = "STALE"
SNAPSHOT_FAILED = "FAILED"

Number = Union[int, float]


def _clean_reason(reason: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(reason, dict):
        return None
    return dict(reason)


@dataclass
class StrategyMembership:
    """Independent per-strategy admissibility for one symbol."""

    strategy: str
    status: str = MEMBERSHIP_NOT_EVALUATED
    primary_reason: Optional[Dict[str, Any]] = None
    supporting_reasons: List[Dict[str, Any]] = field(default_factory=list)
    measured: Optional[Number] = None
    threshold: Optional[Union[Number, List[Number]]] = None
    unit: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "status": self.status,
            "primary_reason": _clean_reason(self.primary_reason),
            "supporting_reasons": [dict(r) for r in (self.supporting_reasons or []) if isinstance(r, dict)],
            "measured": self.measured,
            "threshold": self.threshold,
            "unit": self.unit,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StrategyMembership":
        return cls(
            strategy=str(d.get("strategy") or ""),
            status=str(d.get("status") or MEMBERSHIP_NOT_EVALUATED),
            primary_reason=_clean_reason(d.get("primary_reason")),
            supporting_reasons=[dict(r) for r in (d.get("supporting_reasons") or []) if isinstance(r, dict)],
            measured=d.get("measured"),
            threshold=d.get("threshold"),
            unit=d.get("unit"),
        )


@dataclass
class LifecycleTransition:
    """One recorded lifecycle state change."""

    from_state: Optional[str]
    to_state: str
    reason_code: str
    at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason_code": self.reason_code,
            "at_utc": self.at_utc,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LifecycleTransition":
        return cls(
            from_state=d.get("from_state"),
            to_state=str(d.get("to_state") or ""),
            reason_code=str(d.get("reason_code") or ""),
            at_utc=str(d.get("at_utc") or ""),
        )


@dataclass
class ManualOverride:
    """Explicit, logged, reversible manual override (mirrors the effective overlay).

    An INCLUDE override can never bypass a safety-critical quarantine.
    """

    kind: str  # INCLUDE | EXCLUDE
    reason: Optional[str] = None
    at_utc: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "reason": self.reason, "at_utc": self.at_utc}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ManualOverride":
        return cls(
            kind=str(d.get("kind") or ""),
            reason=d.get("reason"),
            at_utc=d.get("at_utc"),
        )


@dataclass
class UniverseV2Record:
    """One symbol's full universe-v2 state."""

    symbol: str
    in_research_pool: bool = True
    lifecycle_state: str = LIFECYCLE_WATCH
    memberships: Dict[str, StrategyMembership] = field(default_factory=dict)
    primary_reason: Optional[Dict[str, Any]] = None
    supporting_reasons: List[Dict[str, Any]] = field(default_factory=list)
    safety_critical: bool = False
    temporary: bool = False
    pass_streak: int = 0
    fail_streak: int = 0
    last_transition: Optional[LifecycleTransition] = None
    evaluation_version: Optional[str] = None
    data_source: Optional[str] = None
    as_of_utc: Optional[str] = None
    manual_override: Optional[ManualOverride] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "in_research_pool": self.in_research_pool,
            "lifecycle_state": self.lifecycle_state,
            "memberships": {k: v.to_dict() for k, v in self.memberships.items()},
            "primary_reason": _clean_reason(self.primary_reason),
            "supporting_reasons": [dict(r) for r in (self.supporting_reasons or []) if isinstance(r, dict)],
            "safety_critical": self.safety_critical,
            "temporary": self.temporary,
            "pass_streak": self.pass_streak,
            "fail_streak": self.fail_streak,
            "last_transition": self.last_transition.to_dict() if self.last_transition else None,
            "evaluation_version": self.evaluation_version,
            "data_source": self.data_source,
            "as_of_utc": self.as_of_utc,
            "manual_override": self.manual_override.to_dict() if self.manual_override else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UniverseV2Record":
        mem_raw = d.get("memberships") or {}
        memberships = {
            str(k): StrategyMembership.from_dict(v)
            for k, v in mem_raw.items()
            if isinstance(v, dict)
        }
        lt = d.get("last_transition")
        mo = d.get("manual_override")
        return cls(
            symbol=str(d.get("symbol") or "").strip().upper(),
            in_research_pool=bool(d.get("in_research_pool", True)),
            lifecycle_state=str(d.get("lifecycle_state") or LIFECYCLE_WATCH),
            memberships=memberships,
            primary_reason=_clean_reason(d.get("primary_reason")),
            supporting_reasons=[dict(r) for r in (d.get("supporting_reasons") or []) if isinstance(r, dict)],
            safety_critical=bool(d.get("safety_critical", False)),
            temporary=bool(d.get("temporary", False)),
            pass_streak=int(d.get("pass_streak") or 0),
            fail_streak=int(d.get("fail_streak") or 0),
            last_transition=LifecycleTransition.from_dict(lt) if isinstance(lt, dict) else None,
            evaluation_version=d.get("evaluation_version"),
            data_source=d.get("data_source"),
            as_of_utc=d.get("as_of_utc"),
            manual_override=ManualOverride.from_dict(mo) if isinstance(mo, dict) else None,
        )


@dataclass
class UniverseV2Snapshot:
    """Published, versioned universe-v2 read snapshot."""

    version: int
    created_at_utc: str
    status: str = SNAPSHOT_COMPLETE
    schema_version: str = SCHEMA_VERSION
    source_evaluation_version: Optional[str] = None
    research_pool_count: int = 0
    records: List[UniverseV2Record] = field(default_factory=list)
    counts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "created_at_utc": self.created_at_utc,
            "status": self.status,
            "source_evaluation_version": self.source_evaluation_version,
            "research_pool_count": self.research_pool_count,
            "records": [r.to_dict() for r in self.records],
            "counts": self.counts,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UniverseV2Snapshot":
        return cls(
            version=int(d.get("version") or 0),
            created_at_utc=str(d.get("created_at_utc") or ""),
            status=str(d.get("status") or SNAPSHOT_COMPLETE),
            schema_version=str(d.get("schema_version") or SCHEMA_VERSION),
            source_evaluation_version=d.get("source_evaluation_version"),
            research_pool_count=int(d.get("research_pool_count") or 0),
            records=[UniverseV2Record.from_dict(r) for r in (d.get("records") or []) if isinstance(r, dict)],
            counts=dict(d.get("counts") or {}),
        )
