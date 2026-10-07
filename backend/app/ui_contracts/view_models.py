# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""UI view models: JSON-serializable read contracts (Phase 6.5)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class PositionView:
    """What the UI needs for one position (open or closed)."""

    position_id: Union[int, str]
    symbol: str
    strategy_type: str
    lifecycle_state: str
    opened: str  # date YYYY-MM-DD
    expiry: Optional[str]
    strike: Optional[Union[float, tuple]]  # single or (short, long)
    contracts: int
    entry_credit: Optional[float]
    last_mark: Optional[float]
    dte: Optional[int]
    unrealized_pnl: Optional[float]
    realized_pnl: float
    max_loss_estimate: Optional[float]
    profit_targets: Dict[str, float]  # t1, t2, t3 = option premium to close at
    notes: str
    needs_attention: bool
    attention_reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("strike"), tuple):
            d["strike"] = list(d["strike"])
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PositionView":
        strike = data.get("strike")
        if isinstance(strike, list):
            strike = tuple(strike) if strike else None
        return cls(
            position_id=data["position_id"],
            symbol=data["symbol"],
            strategy_type=data.get("strategy_type", "CSP"),
            lifecycle_state=data.get("lifecycle_state", "OPEN"),
            opened=data["opened"],
            expiry=data.get("expiry"),
            strike=strike,
            contracts=int(data.get("contracts", 0)),
            entry_credit=data.get("entry_credit"),
            last_mark=data.get("last_mark"),
            dte=data.get("dte"),
            unrealized_pnl=data.get("unrealized_pnl"),
            realized_pnl=float(data.get("realized_pnl", 0)),
            max_loss_estimate=data.get("max_loss_estimate"),
            profit_targets=dict(data.get("profit_targets") or {}),
            notes=str(data.get("notes") or ""),
            needs_attention=bool(data.get("needs_attention", False)),
            attention_reasons=list(data.get("attention_reasons") or []),
        )


@dataclass
class PositionTimelineView:
    """Event timeline + key derived milestones for a position."""

    position_id: str
    symbol: str
    events: List[Dict[str, Any]]  # {event_type, event_time, metadata}
    milestones: Dict[str, Optional[str]]  # first_opened_at, last_event_at, etc.

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PositionTimelineView":
        return cls(
            position_id=data["position_id"],
            symbol=data["symbol"],
            events=list(data.get("events") or []),
            milestones=dict(data.get("milestones") or {}),
        )


@dataclass
class TradePlanView:
    """Proposal + exit plan + targets + readiness + acknowledgment state."""

    decision_ts: str
    symbol: str
    strategy_type: str
    proposal: Dict[str, Any]
    execution_status: str
    user_acknowledged: bool
    execution_notes: str
    exit_plan: Dict[str, Any]
    computed_targets: Dict[str, float]  # t1, t2, t3
    blockers: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradePlanView":
        return cls(
            decision_ts=data["decision_ts"],
            symbol=data["symbol"],
            strategy_type=data.get("strategy_type", "CSP"),
            proposal=dict(data.get("proposal") or {}),
            execution_status=data.get("execution_status", "BLOCKED"),
            user_acknowledged=bool(data.get("user_acknowledged", False)),
            execution_notes=str(data.get("execution_notes") or ""),
            exit_plan=dict(data.get("exit_plan") or {}),
            computed_targets=dict(data.get("computed_targets") or {}),
            blockers=list(data.get("blockers") or []),
        )


@dataclass
class DailyOverviewView:
    """Today's run metadata + why-no-trade + top blockers + counts."""

    date: str
    run_mode: str
    config_frozen: bool
    freeze_violation_changed_keys: List[str]
    regime: Optional[str]
    regime_reason: Optional[str]
    symbols_evaluated: int
    selected_signals: int
    trades_ready: int
    no_trade: bool
    why_summary: str
    top_blockers: List[Dict[str, Any]]  # {code, count}
    risk_posture: str
    links: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyOverviewView":
        return cls(
            date=data.get("date", ""),
            run_mode=data.get("run_mode", "DRY_RUN"),
            config_frozen=bool(data.get("config_frozen", False)),
            freeze_violation_changed_keys=list(data.get("freeze_violation_changed_keys") or []),
            regime=data.get("regime"),
            regime_reason=data.get("regime_reason"),
            symbols_evaluated=int(data.get("symbols_evaluated", 0)),
            selected_signals=int(data.get("selected_signals", 0)),
            trades_ready=int(data.get("trades_ready", 0)),
            no_trade=bool(data.get("no_trade", True)),
            why_summary=str(data.get("why_summary") or ""),
            top_blockers=list(data.get("top_blockers") or []),
            risk_posture=str(data.get("risk_posture") or "CONSERVATIVE"),
            links=dict(data.get("links") or {}),
        )


@dataclass
class PerformanceSummaryView:
    """Month-to-date and monthly summaries from ledger."""

    as_of: str
    mtd_realized_pnl: float
    capital_deployed_today: float
    monthly: Dict[str, Any]  # current month from compute_monthly_summary
    last_3_months: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AlertsView:
    """What needs operator attention now."""

    as_of: str
    items: List[Dict[str, Any]]  # {level, code, message, symbol, position_id?, decision_ts?}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
