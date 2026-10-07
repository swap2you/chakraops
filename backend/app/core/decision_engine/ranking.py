# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Deterministic ranking and recommendation selection (R33.0).

Separates candidates into actionable / watch / blocked, ranks actionable
candidates deterministically, and caps the actionable list to the profile's
top 5–7. Tie-breaking is fully deterministic so the same inputs always yield
the same ordering.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from app.core.decision_engine.contract import (
    ACTIONABLE,
    BLOCKED,
    DecisionOutput,
    WATCH,
)


def _sort_key(o: DecisionOutput) -> Tuple:
    # Higher score first, then higher expected $ return, then stable A→Z.
    ret_dollars = o.expected_return_dollars if o.expected_return_dollars is not None else -1.0
    return (-o.score, -ret_dollars, o.symbol, o.strategy)


def rank_outputs(outputs: List[DecisionOutput], max_recommendations: int) -> Dict[str, List[DecisionOutput]]:
    """Partition and rank decision outputs deterministically.

    Returns a dict with ``actionable`` (ranked, capped), ``watch``, and
    ``blocked`` lists. Ranks (1..N) are assigned only to actionable items.
    """
    actionable = [o for o in outputs if o.decision_status == ACTIONABLE]
    watch = [o for o in outputs if o.decision_status == WATCH]
    blocked = [o for o in outputs if o.decision_status == BLOCKED]

    actionable.sort(key=_sort_key)
    capped = actionable[: max(1, int(max_recommendations))]

    ranked: List[DecisionOutput] = []
    for i, o in enumerate(capped, start=1):
        ranked.append(
            DecisionOutput(
                symbol=o.symbol,
                strategy=o.strategy,
                profile=o.profile,
                market_regime=o.market_regime,
                decision_status=o.decision_status,
                eligibility=o.eligibility,
                data_quality=o.data_quality,
                data_freshness=o.data_freshness,
                event_risk=o.event_risk,
                selected_contract=o.selected_contract,
                sizing=o.sizing,
                capital_required=o.capital_required,
                expected_return_pct=o.expected_return_pct,
                expected_return_dollars=o.expected_return_dollars,
                risk_flags=o.risk_flags,
                score=o.score,
                rank=i,
                reason_codes=o.reason_codes,
                manual_only=o.manual_only,
            )
        )

    # Actionable beyond the cap fall through to the watch list (still useful,
    # not noisy in the primary recommendation set).
    overflow = actionable[len(capped):]
    watch_sorted = sorted(watch + overflow, key=lambda o: (o.symbol, o.strategy, -o.score))
    blocked_sorted = sorted(blocked, key=lambda o: (o.symbol, o.strategy))

    return {"actionable": ranked, "watch": watch_sorted, "blocked": blocked_sorted}
