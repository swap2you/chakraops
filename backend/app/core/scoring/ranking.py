# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.2: Priority ranking (informational only). Does not change mode_decision or Stage-2."""

from __future__ import annotations

from typing import Any, Dict, List

TIER_ORDER = {"A": 3, "B": 2, "C": 1, "NONE": 0}


def rank_candidates(candidate_payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Rank candidates by tier (A > B > C), then composite_score desc, affordability_score desc, liquidity_score desc.
    Returns new list with priority_rank 1..N assigned. Does not mutate inputs.
    """
    payloads = [dict(p) for p in candidate_payloads]
    score_block = lambda p: p.get("score") or {}
    tier_val = lambda p: TIER_ORDER.get((p.get("tier") or "NONE").strip().upper(), 0)
    comp = lambda p: float(score_block(p).get("composite_score") or 0)
    aff = lambda p: float(score_block(p).get("components", {}).get("affordability_score") or 0)
    liq = lambda p: (score_block(p).get("components") or {}).get("liquidity_score")
    liq_val = lambda p: float(liq(p)) if liq(p) is not None else -1.0

    def key(p: Dict[str, Any]) -> tuple:
        return (
            -tier_val(p),
            -comp(p),
            -aff(p),
            -liq_val(p),
        )

    payloads.sort(key=key)
    for i, p in enumerate(payloads):
        p["priority_rank"] = i + 1
    return payloads
