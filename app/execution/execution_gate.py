from __future__ import annotations

"""Execution gate (Phase 5 Step 1).

Pure, deterministic logic that evaluates whether execution should be allowed
based on a DecisionSnapshot. No I/O, no logging, no persistence.

This gate provides explicit, stable reason strings for audit purposes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from app.signals.decision_snapshot import DecisionSnapshot


@dataclass(frozen=True)
class ExecutionGateResult:
    """Result of execution gate evaluation."""

    allowed: bool
    reasons: List[str] = field(default_factory=list)


def evaluate_execution_gate(
    snapshot: DecisionSnapshot,
    max_age_minutes: float = 5.0,
) -> ExecutionGateResult:
    """Evaluate whether execution should be allowed based on DecisionSnapshot.

    This function applies deterministic rules to block execution if:
    - No selected signals exist
    - Selected signals violate policy constraints
    - Snapshot is stale
    - No symbols were evaluated

    Args:
        snapshot: DecisionSnapshot from signal engine
        max_age_minutes: Maximum age of snapshot in minutes (default: 5.0)

    Returns:
        ExecutionGateResult with allowed flag and explicit reason strings
    """
    reasons: List[str] = []

    # Rule 1: Check if selected_signals exists and is non-empty
    if snapshot.selected_signals is None or len(snapshot.selected_signals) == 0:
        reasons.append("NO_SELECTED_SIGNALS")
        return ExecutionGateResult(allowed=False, reasons=reasons)

    # Rule 2: Check if any selected signal violates min_score policy
    # Extract min_score from policy_snapshot in explanations (if present)
    if snapshot.explanations and len(snapshot.explanations) > 0:
        policy_snapshot = snapshot.explanations[0].get("policy_snapshot", {})
        min_score_policy = policy_snapshot.get("min_score")
        if min_score_policy is not None:
            for selected in snapshot.selected_signals:
                scored_dict = selected.get("scored", {})
                score_dict = scored_dict.get("score", {})
                score_total = score_dict.get("total")
                if score_total is not None and score_total < min_score_policy:
                    reasons.append(
                        f"SIGNAL_SCORE_BELOW_MIN: score={score_total}, min={min_score_policy}"
                    )
                    return ExecutionGateResult(allowed=False, reasons=reasons)

    # Rule 3: Check if selected_signals count exceeds policy max_total
    if snapshot.explanations and len(snapshot.explanations) > 0:
        policy_snapshot = snapshot.explanations[0].get("policy_snapshot", {})
        max_total_policy = policy_snapshot.get("max_total")
        if max_total_policy is not None:
            selected_count = len(snapshot.selected_signals)
            if selected_count > max_total_policy:
                reasons.append(
                    f"SELECTED_COUNT_EXCEEDS_MAX: count={selected_count}, max={max_total_policy}"
                )
                return ExecutionGateResult(allowed=False, reasons=reasons)

    # Rule 4: Check if no symbols were evaluated
    symbols_evaluated = snapshot.stats.get("symbols_evaluated", 0)
    if symbols_evaluated == 0:
        reasons.append("NO_SYMBOLS_EVALUATED")
        return ExecutionGateResult(allowed=False, reasons=reasons)

    # Rule 5: Check if snapshot is stale (as_of is older than threshold)
    try:
        as_of_dt = datetime.fromisoformat(snapshot.as_of)
        now = datetime.now(as_of_dt.tzinfo) if as_of_dt.tzinfo else datetime.now()
        age_delta = now - as_of_dt
        age_minutes = age_delta.total_seconds() / 60.0

        if age_minutes > max_age_minutes:
            reasons.append(
                f"SNAPSHOT_STALE: age_minutes={age_minutes:.2f}, max={max_age_minutes}"
            )
            return ExecutionGateResult(allowed=False, reasons=reasons)
    except (ValueError, TypeError):
        # If as_of cannot be parsed, treat as stale
        reasons.append("SNAPSHOT_AS_OF_INVALID")
        return ExecutionGateResult(allowed=False, reasons=reasons)

    # All checks passed
    return ExecutionGateResult(allowed=True, reasons=[])


__all__ = ["ExecutionGateResult", "evaluate_execution_gate"]
