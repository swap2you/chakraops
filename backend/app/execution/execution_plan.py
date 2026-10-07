from __future__ import annotations

"""Execution plan builder (Phase 5 Step 2).

Pure, deterministic logic that builds execution orders from a DecisionSnapshot
and ExecutionGateResult. No broker calls, no I/O, no logging.

This module converts selected signals into executable orders while preserving
deterministic ordering and providing clear blocked reasons when execution is
not allowed.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from app.execution.execution_gate import ExecutionGateResult
from app.signals.decision_snapshot import DecisionSnapshot


@dataclass(frozen=True)
class ExecutionOrder:
    """Single execution order derived from a selected signal."""

    symbol: str
    action: str  # "SELL_TO_OPEN" for CSP/CC
    strike: float
    expiry: str  # ISO date string
    option_right: str  # "PUT" or "CALL"
    quantity: int
    limit_price: float


@dataclass(frozen=True)
class ExecutionPlan:
    """Execution plan containing orders or blocked reason."""

    allowed: bool
    blocked_reason: Optional[str] = None
    orders: List[ExecutionOrder] = field(default_factory=list)


def build_execution_plan(
    snapshot: DecisionSnapshot,
    gate_result: ExecutionGateResult,
) -> ExecutionPlan:
    """Build execution plan from DecisionSnapshot and gate evaluation result.

    If gate blocks execution, returns plan with allowed=False and first reason.
    If gate allows execution, builds one SELL_TO_OPEN order per selected signal.

    Args:
        snapshot: DecisionSnapshot from signal engine
        gate_result: ExecutionGateResult from execution gate evaluation

    Returns:
        ExecutionPlan with orders (if allowed) or blocked reason (if not allowed)
    """
    # If gate blocks execution, return blocked plan
    if not gate_result.allowed:
        blocked_reason = gate_result.reasons[0] if gate_result.reasons else "EXECUTION_BLOCKED"
        return ExecutionPlan(allowed=False, blocked_reason=blocked_reason, orders=[])

    # Gate allows execution - build orders from selected signals
    if snapshot.selected_signals is None or len(snapshot.selected_signals) == 0:
        return ExecutionPlan(allowed=False, blocked_reason="NO_SELECTED_SIGNALS", orders=[])

    orders: List[ExecutionOrder] = []

    for selected_dict in snapshot.selected_signals:
        # Extract nested candidate data from dict structure
        scored_dict = selected_dict.get("scored", {})
        candidate_dict = scored_dict.get("candidate", {})

        symbol = candidate_dict.get("symbol")
        strike = candidate_dict.get("strike")
        expiry = candidate_dict.get("expiry")
        option_right = candidate_dict.get("option_right")
        mid_price = candidate_dict.get("mid")
        bid_price = candidate_dict.get("bid")

        # Validate required fields
        if symbol is None or strike is None or expiry is None or option_right is None:
            continue  # Skip invalid signals

        # Determine limit price: prefer mid, fallback to bid
        limit_price: Optional[float] = None
        if mid_price is not None:
            limit_price = float(mid_price)
        elif bid_price is not None:
            limit_price = float(bid_price)

        # Skip if no price available
        if limit_price is None:
            continue

        # Convert expiry to ISO string if it's a date object
        expiry_str: str
        if isinstance(expiry, date):
            expiry_str = expiry.isoformat()
        elif isinstance(expiry, str):
            expiry_str = expiry
        else:
            continue  # Skip if expiry cannot be converted

        # Build SELL_TO_OPEN order (both CSP and CC use SELL_TO_OPEN)
        order = ExecutionOrder(
            symbol=str(symbol),
            action="SELL_TO_OPEN",
            strike=float(strike),
            expiry=expiry_str,
            option_right=str(option_right),
            quantity=1,
            limit_price=limit_price,
        )
        orders.append(order)

    return ExecutionPlan(allowed=True, blocked_reason=None, orders=orders)


__all__ = ["ExecutionOrder", "ExecutionPlan", "build_execution_plan"]
