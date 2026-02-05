from __future__ import annotations

"""Signal explainability snapshot (Phase 4B Step 1).

This module builds read-only explanation snapshots for selected signals.
It does NOT modify generation, scoring, or selection logic.

Explanations provide:
- Score breakdown (components and weights)
- Selection policy snapshot
- Deterministic, serializable output
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from app.signals.scoring import ScoreComponent
from app.signals.selection import SelectedSignal, SelectionConfig


@dataclass(frozen=True)
class SignalExplanation:
    """Read-only explanation snapshot for a selected signal.

    All fields are deterministic and serializable (no complex objects).
    """

    symbol: str
    signal_type: str
    rank: int
    total_score: float
    score_components: List[ScoreComponent]
    selection_reason: str
    policy_snapshot: Dict[str, Any]


def build_explanations(
    selected_signals: List[SelectedSignal],
    selection_config: SelectionConfig,
) -> List[SignalExplanation]:
    """Build explanation snapshots for selected signals.

    Preserves the order of selected_signals and creates a deterministic
    policy_snapshot from the selection_config.

    Args:
        selected_signals: List of selected signals (already ordered)
        selection_config: Selection policy configuration used

    Returns:
        List of SignalExplanation objects in the same order as selected_signals
    """
    explanations: List[SignalExplanation] = []

    # Build policy snapshot (deterministic dict)
    policy_snapshot: Dict[str, Any] = {
        "max_total": selection_config.max_total,
        "max_per_symbol": selection_config.max_per_symbol,
        "max_per_signal_type": selection_config.max_per_signal_type,
        "min_score": selection_config.min_score,
    }

    for selected in selected_signals:
        scored = selected.scored
        candidate = scored.candidate

        explanation = SignalExplanation(
            symbol=candidate.symbol,
            signal_type=candidate.signal_type.value,
            rank=scored.rank if scored.rank is not None else 0,
            total_score=scored.score.total,
            score_components=list(scored.score.components),
            selection_reason=selected.selection_reason,
            policy_snapshot=policy_snapshot,
        )
        explanations.append(explanation)

    return explanations


__all__ = ["SignalExplanation", "build_explanations"]
