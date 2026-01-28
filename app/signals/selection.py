from __future__ import annotations

"""Signal selection policy (Phase 4A Step 2).

This module operates on *scored* signal candidates and applies a deterministic,
explainable selection policy. It does NOT modify candidate generation,
ordering, or scoring logic.
"""

from dataclasses import dataclass
from typing import Dict, List, Sequence

from app.signals.models import SignalType
from app.signals.scoring import ScoredSignalCandidate


@dataclass(frozen=True)
class SelectionConfig:
    """Selection policy configuration (post-scoring).

    All caps are applied in rank order over the input scored list, which is
    assumed to be already sorted by descending score (and tie-breakers).
    """

    max_total: int
    max_per_symbol: int
    max_per_signal_type: int | None
    min_score: float | None


@dataclass(frozen=True)
class SelectedSignal:
    """Signal selected for further processing or presentation."""

    scored: ScoredSignalCandidate
    selection_reason: str


def select_signals(
    scored_candidates: Sequence[ScoredSignalCandidate],
    config: SelectionConfig,
) -> List[SelectedSignal]:
    """Apply selection policy to a ranked list of scored candidates.

    The input list is treated as immutable and already sorted by score/rank.
    Selection proceeds in this order:
    1. Filter out candidates with score.total < min_score (if configured)
    2. Enforce per-symbol cap
    3. Enforce per-signal-type cap
    4. Enforce total cap

    The result is deterministic given the same inputs.
    """
    if not scored_candidates:
        return []

    selected: List[SelectedSignal] = []
    counts_by_symbol: Dict[str, int] = {}
    counts_by_type: Dict[SignalType, int] = {}

    # Helper to check caps without mutating counts
    def _can_select(symbol: str, stype: SignalType) -> bool:
        # Per-symbol cap
        sym_count = counts_by_symbol.get(symbol, 0)
        if sym_count >= config.max_per_symbol:
            return False

        # Per-signal-type cap (if enabled)
        if config.max_per_signal_type is not None:
            type_count = counts_by_type.get(stype, 0)
            if type_count >= config.max_per_signal_type:
                return False

        # Total cap
        if len(selected) >= config.max_total:
            return False

        return True

    for scored in scored_candidates:
        # Stop early if total cap already reached
        if len(selected) >= config.max_total:
            break

        total_score = scored.score.total

        # a) min_score filter
        if config.min_score is not None and total_score < config.min_score:
            continue

        symbol = scored.candidate.symbol
        stype = scored.candidate.signal_type

        # b/c/d) caps
        if not _can_select(symbol, stype):
            continue

        # Update counters
        counts_by_symbol[symbol] = counts_by_symbol.get(symbol, 0) + 1
        counts_by_type[stype] = counts_by_type.get(stype, 0) + 1

        # Deterministic, simple selection reason
        reason = "SELECTED_BY_POLICY"
        selected.append(SelectedSignal(scored=scored, selection_reason=reason))

    return selected


__all__ = ["SelectionConfig", "SelectedSignal", "select_signals"]

