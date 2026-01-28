from __future__ import annotations

"""Dry-run executor (Phase 5 Step 3).

Pure logic that simulates execution without broker calls, I/O, or logging.
This is a deterministic pass-through that adds an execution timestamp.

In a dry-run, orders are not actually sent to a broker - they are simply
recorded with a timestamp for audit and testing purposes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from app.execution.execution_plan import ExecutionOrder, ExecutionPlan


@dataclass(frozen=True)
class DryRunExecutionResult:
    """Result of a dry-run execution."""

    allowed: bool
    blocked_reason: Optional[str]
    orders: List[ExecutionOrder]
    executed_at: str  # ISO datetime string


def execute_dry_run(plan: ExecutionPlan) -> DryRunExecutionResult:
    """Execute a dry-run of an execution plan.

    This function does not make broker calls or perform I/O. It simply
    passes through the plan's data and adds an execution timestamp.

    Args:
        plan: ExecutionPlan to execute (dry-run)

    Returns:
        DryRunExecutionResult with plan data and executed_at timestamp
    """
    executed_at = datetime.now().isoformat()

    return DryRunExecutionResult(
        allowed=plan.allowed,
        blocked_reason=plan.blocked_reason,
        orders=list(plan.orders),  # Create new list to avoid mutation
        executed_at=executed_at,
    )


__all__ = ["DryRunExecutionResult", "execute_dry_run"]
