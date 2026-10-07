# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options context gating (Phase 3.2): IV rank, expected move, event proximity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.signals.models import ExclusionReason, SignalType
from app.signals.scoring import ScoredSignalCandidate


@dataclass(frozen=True)
class ContextGateConfig:
    """Configuration for options context gating.

    Selling (CSP, CC): block when IV rank < iv_rank_min_sell_pct or > iv_rank_max_sell_pct.
    Buying: block when IV rank > iv_rank_max_buy_pct (for later phases).
    Block when expected 1sd move > distance from underlying to short strike.
    Block when earnings or macro event within dte_event_window days.
    """

    iv_rank_min_sell_pct: float  # e.g. 10: block selling when IV rank < 10
    iv_rank_max_sell_pct: float  # e.g. 90: block selling when IV rank > 90
    iv_rank_max_buy_pct: float   # e.g. 70: block buying when IV rank > 70
    dte_event_window: int       # block if earnings/event within this many days
    expected_move_gate: bool     # block if expected_move_1sd * underlying > distance to strike


def _check_context_gate(
    scored: ScoredSignalCandidate,
    config: ContextGateConfig,
) -> Optional[ExclusionReason]:
    """Return an ExclusionReason if the candidate fails context gate; else None."""
    c = scored.candidate
    symbol = c.symbol
    stype = c.signal_type
    ctx = c.option_context

    # No context: do not block (gate is best-effort)
    if ctx is None:
        return None

    # Use IV rank from option_context; fallback to candidate.iv_rank (0-100 scale)
    iv_rank = ctx.iv_rank if getattr(ctx, "iv_rank", None) is not None else c.iv_rank
    if iv_rank is not None:
        try:
            rank = float(iv_rank)
        except (TypeError, ValueError):
            rank = None
    else:
        rank = None

    # Selling strategies (CSP, CC): block when IV rank in bottom 10% or above 90%
    if stype in (SignalType.CSP, SignalType.CC):
        if rank is not None:
            if rank < config.iv_rank_min_sell_pct:
                return ExclusionReason(
                    code="iv_rank_low_sell",
                    message=(
                        f"IV rank {rank:.1f}% below minimum {config.iv_rank_min_sell_pct}% "
                        f"for selling ({symbol})"
                    ),
                    data={
                        "symbol": symbol,
                        "signal_type": stype.value,
                        "iv_rank": rank,
                        "iv_rank_min_sell_pct": config.iv_rank_min_sell_pct,
                    },
                )
            if rank > config.iv_rank_max_sell_pct:
                return ExclusionReason(
                    code="iv_rank_high_sell",
                    message=(
                        f"IV rank {rank:.1f}% above maximum {config.iv_rank_max_sell_pct}% "
                        f"for selling ({symbol})"
                    ),
                    data={
                        "symbol": symbol,
                        "signal_type": stype.value,
                        "iv_rank": rank,
                        "iv_rank_max_sell_pct": config.iv_rank_max_sell_pct,
                    },
                )

    # Buying strategies (for later): block when IV rank > 70%
    # Current pipeline is CSP/CC only; leave hook in place
    if stype not in (SignalType.CSP, SignalType.CC) and rank is not None:
        if rank > config.iv_rank_max_buy_pct:
            return ExclusionReason(
                code="iv_rank_high_buy",
                message=(
                    f"IV rank {rank:.1f}% above maximum {config.iv_rank_max_buy_pct}% "
                    f"for buying ({symbol})"
                ),
                data={
                    "symbol": symbol,
                    "signal_type": stype.value,
                    "iv_rank": rank,
                    "iv_rank_max_buy_pct": config.iv_rank_max_buy_pct,
                },
            )

    # Expected move: block if expected 1sd move > distance from underlying to short strike
    if config.expected_move_gate and getattr(ctx, "expected_move_1sd", None) is not None:
        try:
            expected_move_1sd = float(ctx.expected_move_1sd)
        except (TypeError, ValueError):
            expected_move_1sd = None
        if expected_move_1sd is not None and expected_move_1sd > 0:
            underlying = float(c.underlying_price)
            strike = float(c.strike)
            if underlying > 0:
                distance = abs(underlying - strike)
                expected_move_dollars = expected_move_1sd * underlying
                if expected_move_dollars > distance:
                    return ExclusionReason(
                        code="expected_move_exceeds_strike_distance",
                        message=(
                            f"Expected 1sd move ${expected_move_dollars:.2f} exceeds "
                            f"distance to strike ${distance:.2f} ({symbol})"
                        ),
                        data={
                            "symbol": symbol,
                            "signal_type": stype.value,
                            "expected_move_1sd": expected_move_1sd,
                            "expected_move_dollars": expected_move_dollars,
                            "underlying_price": underlying,
                            "strike": strike,
                            "distance_to_strike": distance,
                        },
                    )

    # Event proximity: block if earnings or macro event within dte_event_window days
    days_to_earnings = getattr(ctx, "days_to_earnings", None)
    if days_to_earnings is not None and config.dte_event_window > 0:
        try:
            dte_ern = int(days_to_earnings)
            if 0 <= dte_ern <= config.dte_event_window:
                return ExclusionReason(
                    code="event_within_window",
                    message=(
                        f"Earnings in {dte_ern} days within window {config.dte_event_window} "
                        f"({symbol})"
                    ),
                    data={
                        "symbol": symbol,
                        "signal_type": stype.value,
                        "days_to_earnings": dte_ern,
                        "dte_event_window": config.dte_event_window,
                    },
                )
        except (TypeError, ValueError):
            pass

    event_flags = getattr(ctx, "event_flags", None) or []
    if event_flags and config.dte_event_window > 0:
        return ExclusionReason(
            code="event_within_window",
            message=(
                f"Macro event(s) {event_flags} within window ({symbol})"
            ),
            data={
                "symbol": symbol,
                "signal_type": stype.value,
                "event_flags": list(event_flags),
                "dte_event_window": config.dte_event_window,
            },
        )

    return None


def apply_context_gate(
    scored_candidates: Sequence[ScoredSignalCandidate],
    config: ContextGateConfig,
) -> Tuple[List[ScoredSignalCandidate], List[ExclusionReason]]:
    """Filter scored candidates by options context; return (passed, context_exclusions)."""
    passed: List[ScoredSignalCandidate] = []
    context_exclusions: List[ExclusionReason] = []

    for scored in scored_candidates:
        reason = _check_context_gate(scored, config)
        if reason is not None:
            context_exclusions.append(reason)
            continue
        passed.append(scored)

    return passed, context_exclusions


__all__ = ["ContextGateConfig", "apply_context_gate", "_check_context_gate"]
