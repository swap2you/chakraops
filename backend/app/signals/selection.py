from __future__ import annotations

"""Signal selection policy (Phase 4A Step 2). Phase 3.2: options context gating.

This module operates on *scored* signal candidates and applies a deterministic,
explainable selection policy. It does NOT modify candidate generation,
ordering, or scoring logic. Phase 2.4: confidence gating filters out candidates
below min_confidence_threshold using the existing confidence engine.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from app.core.confidence_engine import compute_confidence
from app.signals.context_gating import ContextGateConfig, apply_context_gate
from app.signals.models import ExclusionReason, SignalType
from app.signals.scoring import ScoredSignalCandidate
from app.signals.utils import calc_dte


@dataclass(frozen=True)
class SelectionConfig:
    """Selection policy configuration (post-scoring).

    All caps are applied in rank order over the input scored list, which is
    assumed to be already sorted by descending score (and tie-breakers).
    Phase 2.4: when min_confidence_threshold is set, candidates with
    confidence score below it are excluded (confidence_below_threshold).
    """

    max_total: int
    max_per_symbol: int
    max_per_signal_type: int | None
    min_score: float | None
    min_confidence_threshold: int | None = None  # Phase 2.4: gate by confidence (0-100)
    context_gate: ContextGateConfig | None = None  # Phase 3.2: IV rank, expected move, event window


@dataclass(frozen=True)
class SelectedSignal:
    """Signal selected for further processing or presentation."""

    scored: ScoredSignalCandidate
    selection_reason: str


def select_signals(
    scored_candidates: Sequence[ScoredSignalCandidate],
    config: SelectionConfig,
    confidence_context: Dict[str, Any] | None = None,
) -> Tuple[List[SelectedSignal], List[ExclusionReason]]:
    """Apply selection policy to a ranked list of scored candidates.

    The input list is treated as immutable and already sorted by score/rank.
    Selection proceeds in this order:
    0. (Phase 3.2) Filter by options context gate (IV rank, expected move, event window)
    1. (Phase 2.4) Filter out candidates with confidence score < min_confidence_threshold
    2. Filter out candidates with score.total < min_score (if configured)
    3. Enforce per-symbol cap
    4. Enforce per-signal-type cap
    5. Enforce total cap

    Returns (selected_signals, exclusions). Exclusions include context and
    confidence exclusions; merge into result.exclusions for decision snapshots.
    """
    if not scored_candidates:
        return [], []

    # Phase 3.2: options context gate first
    candidates_to_consider = list(scored_candidates)
    all_exclusions: List[ExclusionReason] = []
    if config.context_gate is not None:
        candidates_to_consider, context_exclusions = apply_context_gate(
            scored_candidates, config.context_gate
        )
        all_exclusions.extend(context_exclusions)

    selected: List[SelectedSignal] = []
    counts_by_symbol: Dict[str, int] = {}
    counts_by_type: Dict[SignalType, int] = {}

    # Default context for confidence when not provided (do not change confidence calculation)
    ctx = confidence_context or {}
    regime_confidence = ctx.get("regime_confidence", 50)
    ema200 = ctx.get("ema200")
    if ema200 is None and isinstance(ctx.get("ema200_by_symbol"), dict):
        pass  # per-symbol below
    system_health = ctx.get("system_health_status") or ctx.get("system_health")

    def _can_select(symbol: str, stype: SignalType) -> bool:
        sym_count = counts_by_symbol.get(symbol, 0)
        if sym_count >= config.max_per_symbol:
            return False
        if config.max_per_signal_type is not None:
            type_count = counts_by_type.get(stype, 0)
            if type_count >= config.max_per_signal_type:
                return False
        if len(selected) >= config.max_total:
            return False
        return True

    for scored in candidates_to_consider:
        if len(selected) >= config.max_total:
            break

        c = scored.candidate
        symbol = c.symbol
        stype = c.signal_type

        # Confidence gate (Phase 2.4)
        if config.min_confidence_threshold is not None:
            ema200_sym = ema200
            if ema200_sym is None and isinstance(ctx.get("ema200_by_symbol"), dict):
                ema200_sym = (ctx.get("ema200_by_symbol") or {}).get(symbol)
            dte = calc_dte(c.as_of, c.expiry)
            confidence_score = compute_confidence(
                symbol=symbol,
                regime_confidence=regime_confidence,
                price=c.underlying_price,
                ema200=ema200_sym,
                dte=dte,
                premium_collected_pct=None,
                system_health_status=system_health,
            )
            if confidence_score.score < config.min_confidence_threshold:
                all_exclusions.append(
                    ExclusionReason(
                        code="confidence_below_threshold",
                        message=(
                            f"Confidence score {confidence_score.score} below threshold "
                            f"{config.min_confidence_threshold} for {symbol}"
                        ),
                        data={
                            "symbol": symbol,
                            "signal_type": stype.value,
                            "confidence_score": confidence_score.score,
                            "min_confidence_threshold": config.min_confidence_threshold,
                        },
                    )
                )
                continue

        total_score = scored.score.total

        # a) min_score filter
        if config.min_score is not None and total_score < config.min_score:
            continue

        # b/c/d) caps
        if not _can_select(symbol, stype):
            continue

        counts_by_symbol[symbol] = counts_by_symbol.get(symbol, 0) + 1
        counts_by_type[stype] = counts_by_type.get(stype, 0) + 1
        selected.append(SelectedSignal(scored=scored, selection_reason="SELECTED_BY_POLICY"))

    return selected, all_exclusions


__all__ = ["SelectionConfig", "SelectedSignal", "select_signals"]

