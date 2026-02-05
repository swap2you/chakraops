# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""TradeProposal: deterministic output of the trade construction engine (Phase 4.1).

No execution logic; risk-first rejection when rules fail.
Phase 4.3: execution_status, user_acknowledged, execution_notes for human controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional, Tuple, Union


StrategyType = Literal["CSP", "BullPutSpread", "BearCallSpread", "IRON_CONDOR"]

ExecutionStatus = Literal["READY", "REVIEW", "BLOCKED"]


@dataclass(frozen=True)
class TradeProposal:
    """Proposal for a single trade, or explicit NO_TRADE (rejected=True).

    Phase 4.3: execution_status is READY only when not rejected and gate allowed;
    user_acknowledged and execution_notes support human-in-the-loop controls.
    """

    symbol: str
    strategy_type: StrategyType
    expiry: date
    strikes: Union[float, Tuple[float, ...]]  # single strike or (short, long) for spreads
    contracts: int
    credit_estimate: float
    max_loss: float
    expected_move_1sd: Optional[float] = None
    distance_to_risk: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    construction_reason: str = ""
    rejected: bool = False
    rejection_reason: Optional[str] = None
    # Phase 4.3: execution readiness and human controls
    execution_status: ExecutionStatus = "BLOCKED"
    user_acknowledged: bool = False
    execution_notes: str = ""

    def to_dict(self) -> dict:
        """JSON-serializable dict; date and tuple as ISO string and list."""
        d = {
            "symbol": self.symbol,
            "strategy_type": self.strategy_type,
            "expiry": self.expiry.isoformat() if isinstance(self.expiry, date) else str(self.expiry),
            "strikes": list(self.strikes) if isinstance(self.strikes, tuple) else self.strikes,
            "contracts": self.contracts,
            "credit_estimate": self.credit_estimate,
            "max_loss": self.max_loss,
            "expected_move_1sd": self.expected_move_1sd,
            "distance_to_risk": self.distance_to_risk,
            "risk_reward_ratio": self.risk_reward_ratio,
            "construction_reason": self.construction_reason,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
            "execution_status": self.execution_status,
            "user_acknowledged": self.user_acknowledged,
            "execution_notes": self.execution_notes,
        }
        return d


def set_execution_readiness(proposal: TradeProposal, gate_allowed: bool) -> TradeProposal:
    """Set execution_status from proposal and gate. READY only when not rejected and gate allowed."""
    if proposal.rejected or not gate_allowed:
        status: ExecutionStatus = "BLOCKED"
    else:
        status = "READY"
    return TradeProposal(
        symbol=proposal.symbol,
        strategy_type=proposal.strategy_type,
        expiry=proposal.expiry,
        strikes=proposal.strikes,
        contracts=proposal.contracts,
        credit_estimate=proposal.credit_estimate,
        max_loss=proposal.max_loss,
        expected_move_1sd=proposal.expected_move_1sd,
        distance_to_risk=proposal.distance_to_risk,
        risk_reward_ratio=proposal.risk_reward_ratio,
        construction_reason=proposal.construction_reason,
        rejected=proposal.rejected,
        rejection_reason=proposal.rejection_reason,
        execution_status=status,
        user_acknowledged=proposal.user_acknowledged,
        execution_notes=proposal.execution_notes,
    )


def trade_proposal_from_dict(data: dict) -> Optional[TradeProposal]:
    """Build TradeProposal from dict (e.g. JSON). Returns None if missing required fields."""
    if not data or not data.get("symbol"):
        return None
    expiry_val = data.get("expiry")
    if isinstance(expiry_val, str):
        try:
            expiry = date.fromisoformat(expiry_val[:10])
        except ValueError:
            return None
    else:
        return None
    strikes_val = data.get("strikes")
    if isinstance(strikes_val, list):
        strikes: Union[float, Tuple[float, ...]] = tuple(float(s) for s in strikes_val)
    elif isinstance(strikes_val, (int, float)):
        strikes = float(strikes_val)
    else:
        return None
    return TradeProposal(
        symbol=str(data.get("symbol", "")),
        strategy_type=data.get("strategy_type", "CSP"),
        expiry=expiry,
        strikes=strikes,
        contracts=int(data.get("contracts", 1)),
        credit_estimate=float(data.get("credit_estimate", 0)),
        max_loss=float(data.get("max_loss", 0)),
        expected_move_1sd=data.get("expected_move_1sd"),
        distance_to_risk=data.get("distance_to_risk"),
        risk_reward_ratio=data.get("risk_reward_ratio"),
        construction_reason=str(data.get("construction_reason", "")),
        rejected=bool(data.get("rejected", True)),
        rejection_reason=data.get("rejection_reason"),
        execution_status=data.get("execution_status", "BLOCKED"),
        user_acknowledged=bool(data.get("user_acknowledged", False)),
        execution_notes=str(data.get("execution_notes", "")),
    )


__all__ = ["TradeProposal", "StrategyType", "ExecutionStatus", "set_execution_readiness", "trade_proposal_from_dict"]
