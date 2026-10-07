from __future__ import annotations

"""Signal scoring and ranking (Phase 4A).

This module scores immutable `SignalCandidate` objects produced by the
Phase 3 CSP/CC generators. It MUST NOT modify candidate generation logic.

Responsibilities (v1):
- Compute per-candidate component scores in [0.0, 1.0]
- Combine components into a weighted total score
- Return ranked `ScoredSignalCandidate` list with deterministic ordering

No filtering, no execution, no external providers.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Sequence

from app.signals.models import SignalCandidate, SignalType
from app.signals.utils import calc_dte, mid, spread_pct


@dataclass(frozen=True)
class ScoreComponent:
    """Single scoring component contributing to a signal's total score."""

    name: str
    value: float  # already normalized to [0.0, 1.0]
    weight: float


@dataclass(frozen=True)
class SignalScore:
    """Composite score made up of weighted components."""

    total: float
    components: List[ScoreComponent] = field(default_factory=list)


@dataclass(frozen=True)
class ScoredSignalCandidate:
    """Signal candidate annotated with score and optional rank."""

    candidate: SignalCandidate
    score: SignalScore
    rank: int | None


@dataclass(frozen=True)
class ScoringConfig:
    """Configuration for scoring weights.

    All component scores are clamped to [0.0, 1.0] before weighting.
    The total score is:

        total = sum(component.value * component.weight)

    and is rounded to 6 decimal places for deterministic comparison.
    Phase 3.2: context_weight favours moderate IV rank, steep term structure, low skew.
    """

    premium_weight: float
    dte_weight: float
    spread_weight: float
    otm_weight: float
    liquidity_weight: float
    context_weight: float = 0.0  # Phase 3.2: option context (IV rank, term structure, skew)
    # Phase 3.3: strategy selection (prefer credit when IV high; term/skew for neutral bias)
    strategy_preference_weight: float = 0.0
    strategy_iv_rank_high_pct: float = 60.0  # Prefer credit when IV rank > this
    strategy_iv_rank_low_pct: float = 20.0   # Prefer debit when IV rank < this (later)
    strategy_term_slope_backwardation_min: float = 0.0  # Slope above this favours credit
    strategy_term_slope_contango_max: float = 0.0      # Slope below this reduces credit preference


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _compute_premiums(candidates: Sequence[SignalCandidate]) -> List[float]:
    """Extract mid premiums (fallback to bid/ask mid) per candidate."""
    premiums: List[float] = []
    for c in candidates:
        premium = c.mid
        if premium is None:
            premium = mid(c.bid, c.ask)
        premiums.append(float(premium or 0.0))
    return premiums


def _normalize_min_max(values: Sequence[float]) -> List[float]:
    """Normalize values to [0,1] using min-max scaling.

    If all values are equal, returns all 0.0 (no relative preference).
    """
    if not values:
        return []
    v_min = min(values)
    v_max = max(values)
    if v_max <= v_min:
        return [0.0 for _ in values]
    scale = v_max - v_min
    return [(v - v_min) / scale for v in values]


def _compute_otm_value(candidate: SignalCandidate) -> float:
    """Value used for otm_score: prefer prob_otm (0–1) when present, else computed OTM%.

    For CSP (PUT): (underlying - strike) / underlying
    For CC (CALL): (strike - underlying) / underlying
    Negative values floored at 0.0. When prob_otm is set, use it directly (higher = better).
    """
    if candidate.prob_otm is not None:
        return float(candidate.prob_otm)
    underlying = float(candidate.underlying_price)
    if underlying <= 0:
        return 0.0
    if candidate.signal_type == SignalType.CSP:
        raw = (underlying - float(candidate.strike)) / underlying
    else:
        raw = (float(candidate.strike) - underlying) / underlying
    return max(raw, 0.0)


def _compute_dte_scores(
    candidates: Sequence[SignalCandidate],
) -> List[float]:
    """Prefer mid-range DTE using a simple parabolic preference.

    Score is 1.0 at the mid DTE of the set, and 0.0 at the min/max.
    Degenerate cases (all same DTE) get score 0.0.
    """
    if not candidates:
        return []

    dtes: List[int] = []
    for c in candidates:
        dte = calc_dte(c.as_of, c.expiry)
        dtes.append(dte)

    d_min = min(dtes)
    d_max = max(dtes)
    if d_max <= d_min:
        return [0.0 for _ in dtes]

    mid_dte = (d_min + d_max) / 2.0
    half_range = (d_max - d_min) / 2.0
    scores: List[float] = []
    for d in dtes:
        # Parabolic preference: 1 - ((d - mid)/half_range)^2
        x = (d - mid_dte) / half_range
        val = 1.0 - x * x
        scores.append(_clamp01(val))
    return scores


def _compute_spread_scores(candidates: Sequence[SignalCandidate]) -> List[float]:
    """Higher score for tighter spreads (inverse of spread_pct)."""
    spreads: List[float] = []
    for c in candidates:
        sp = spread_pct(c.bid, c.ask)
        # None or non-positive spread treated as best (tight) spread
        spreads.append(float(sp) if sp is not None and sp > 0.0 else 0.0)

    if not spreads:
        return []

    s_max = max(spreads)
    if s_max <= 0.0:
        # All zero spreads => all scores 1.0 (equally best)
        return [1.0 for _ in spreads]

    scores: List[float] = []
    for s in spreads:
        # 0 spread => 1.0, max spread => 0.0
        val = 1.0 - (s / s_max)
        scores.append(_clamp01(val))
    return scores


def _compute_liquidity_scores(candidates: Sequence[SignalCandidate]) -> List[float]:
    """Normalize open interest to [0,1] (higher is better)."""
    ois: List[float] = []
    for c in candidates:
        oi = c.open_interest if c.open_interest is not None else 0
        ois.append(float(oi))

    return _normalize_min_max(ois)


def _compute_context_score(candidate: SignalCandidate) -> float:
    """Compute context score [0,1]: favourable = moderate IV rank, steep term structure, low skew.
    No option_context -> 0.5 (neutral).
    """
    ctx = getattr(candidate, "option_context", None)
    if ctx is None:
        return 0.5

    parts: List[float] = []

    # IV rank: prefer 20-80 (moderate); 0-20 or 80-100 less favourable
    rank = getattr(ctx, "iv_rank", None)
    if rank is not None:
        try:
            r = float(rank)
            if r <= 20:
                iv_score = r / 20.0
            elif r >= 80:
                iv_score = (100.0 - r) / 20.0
            else:
                iv_score = 1.0
            parts.append(_clamp01(iv_score))
        except (TypeError, ValueError):
            pass

    # Term structure slope: for selling, positive (backwardation) can be favourable
    slope = getattr(ctx, "term_structure_slope", None)
    if slope is not None:
        try:
            s = float(slope)
            # Normalize to [0,1]: e.g. slope in [-0.1, 0.1] -> 0.5 + 5*s for positive favour
            term_score = 0.5 + 5.0 * max(-0.1, min(0.1, s))
            parts.append(_clamp01(term_score))
        except (TypeError, ValueError):
            pass

    # Skew: lower abs(skew) often better (less put premium crush)
    skew = getattr(ctx, "skew_metric", None)
    if skew is not None:
        try:
            sk = float(skew)
            skew_score = 1.0 - min(abs(sk) * 10.0, 1.0)
            parts.append(_clamp01(skew_score))
        except (TypeError, ValueError):
            pass

    if not parts:
        return 0.5
    return sum(parts) / len(parts)


def _compute_strategy_preference_score(candidate: SignalCandidate, config: ScoringConfig) -> float:
    """Compute strategy preference score [0,1] for Phase 3.3.

    Credit strategies (CSP, CC): prefer when IV rank high (> iv_rank_high_pct);
    disprefer when IV rank low (< iv_rank_low_pct, debit preferred later).
    Term-structure slope and skew bias toward neutral/balanced: backwardation
    (positive slope) favours credit; balanced skew adds a small boost.
    No option_context or non-credit strategy -> 0.5 (neutral).
    """
    if candidate.signal_type not in (SignalType.CSP, SignalType.CC):
        return 0.5

    ctx = getattr(candidate, "option_context", None)
    if ctx is None:
        return 0.5

    high_pct = getattr(config, "strategy_iv_rank_high_pct", 60.0)
    low_pct = getattr(config, "strategy_iv_rank_low_pct", 20.0)
    back_min = getattr(config, "strategy_term_slope_backwardation_min", 0.0)
    cont_max = getattr(config, "strategy_term_slope_contango_max", 0.0)

    rank = getattr(ctx, "iv_rank", None)
    if rank is None:
        base = 0.5
    else:
        try:
            r = float(rank)
            if r >= high_pct:
                base = 1.0
            elif r <= low_pct:
                base = 0.0
            else:
                base = (r - low_pct) / (high_pct - low_pct) if high_pct > low_pct else 0.5
            base = _clamp01(base)
        except (TypeError, ValueError):
            base = 0.5

    # Term structure: backwardation (slope > back_min) favours credit; contango reduces
    slope = getattr(ctx, "term_structure_slope", None)
    if slope is not None and (back_min != 0.0 or cont_max != 0.0):
        try:
            s = float(slope)
            if s > back_min:
                base = _clamp01(base + 0.05)
            elif s < cont_max:
                base = _clamp01(base - 0.05)
        except (TypeError, ValueError):
            pass

    # Skew: balanced (abs(skew) small) favours neutral/balanced trades
    skew = getattr(ctx, "skew_metric", None)
    if skew is not None:
        try:
            sk = float(skew)
            if abs(sk) < 0.05:
                base = _clamp01(base + 0.03)
            elif abs(sk) > 0.15:
                base = _clamp01(base - 0.02)
        except (TypeError, ValueError):
            pass

    return base


def score_signals(
    candidates: List[SignalCandidate],
    config: ScoringConfig,
) -> List[ScoredSignalCandidate]:
    """Score and rank a list of `SignalCandidate` objects.

    This function:
    - Computes component scores in [0.0, 1.0] for each candidate
    - Applies weights from `ScoringConfig`
    - Computes a total score per candidate (rounded to 6 decimals)
    - Returns a new list of `ScoredSignalCandidate` sorted deterministically

    The input candidate list is not mutated or reordered.
    """
    if not candidates:
        return []

    # Precompute shared values across the candidate set
    premiums = _compute_premiums(candidates)
    premium_scores = _normalize_min_max(premiums)

    dte_scores = _compute_dte_scores(candidates)

    spread_scores = _compute_spread_scores(candidates)

    otm_values: List[float] = [_compute_otm_value(c) for c in candidates]
    otm_scores = _normalize_min_max(otm_values)

    liquidity_scores = _compute_liquidity_scores(candidates)

    context_scores: List[float] = [_compute_context_score(c) for c in candidates]

    strategy_preference_scores: List[float] = [
        _compute_strategy_preference_score(c, config) for c in candidates
    ]

    scored: List[ScoredSignalCandidate] = []
    for idx, c in enumerate(candidates):
        components: List[ScoreComponent] = []

        # premium_score
        p_val = _clamp01(premium_scores[idx])
        components.append(
            ScoreComponent(
                name="premium_score",
                value=p_val,
                weight=config.premium_weight,
            )
        )

        # dte_score
        d_val = _clamp01(dte_scores[idx])
        components.append(
            ScoreComponent(
                name="dte_score",
                value=d_val,
                weight=config.dte_weight,
            )
        )

        # spread_score
        s_val = _clamp01(spread_scores[idx])
        components.append(
            ScoreComponent(
                name="spread_score",
                value=s_val,
                weight=config.spread_weight,
            )
        )

        # otm_score
        o_val = _clamp01(otm_scores[idx])
        components.append(
            ScoreComponent(
                name="otm_score",
                value=o_val,
                weight=config.otm_weight,
            )
        )

        # liquidity_score
        l_val = _clamp01(liquidity_scores[idx])
        components.append(
            ScoreComponent(
                name="liquidity_score",
                value=l_val,
                weight=config.liquidity_weight,
            )
        )

        # context_score (Phase 3.2)
        ctx_val = _clamp01(context_scores[idx])
        components.append(
            ScoreComponent(
                name="context_score",
                value=ctx_val,
                weight=getattr(config, "context_weight", 0.0),
            )
        )

        # strategy_preference_score (Phase 3.3)
        strat_val = _clamp01(strategy_preference_scores[idx])
        components.append(
            ScoreComponent(
                name="strategy_preference_score",
                value=strat_val,
                weight=getattr(config, "strategy_preference_weight", 0.0),
            )
        )

        total = 0.0
        for comp in components:
            total += comp.value * comp.weight

        # Deterministic rounding of total score
        total_rounded = round(total, 6)

        scored.append(
            ScoredSignalCandidate(
                candidate=c,
                score=SignalScore(total=total_rounded, components=components),
                rank=None,  # assigned after sorting
            )
        )

    # Deterministic ordering:
    # - Primary: descending total score
    # - Ties: symbol, signal_type, expiry, strike
    def _sort_key(item: ScoredSignalCandidate):
        c = item.candidate
        return (
            -item.score.total,
            c.symbol,
            c.signal_type.value,
            c.expiry,
            c.strike,
        )

    scored_sorted = sorted(scored, key=_sort_key)

    # Assign ranks (1-based) in sorted order
    ranked: List[ScoredSignalCandidate] = []
    for idx, item in enumerate(scored_sorted, start=1):
        ranked.append(
            ScoredSignalCandidate(
                candidate=item.candidate,
                score=item.score,
                rank=idx,
            )
        )

    return ranked


__all__ = [
    "ScoreComponent",
    "SignalScore",
    "ScoredSignalCandidate",
    "ScoringConfig",
    "score_signals",
]

