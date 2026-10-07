# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Strategy eligibility and deterministic scoring (R33.0).

Covers cash-secured puts (CSP), covered calls (CC), and share buys, plus the
stay-in-cash outcome. Scoring is fully deterministic and documented so golden
vectors are hand-computable. "Soft" rules (delta/DTE range, minimum return)
produce WATCH; "hard" gates (in ``gates.py``) produce BLOCKED.

Option score (0–100) = 0.40*return + 0.25*delta + 0.15*dte + 0.20*liquidity,
each component in [0, 100]:
- return:   clamp((return_pct / min_return_pct) * 40, 0, 100)
- delta:    clamp(100 * (1 - 0.5*|d-center|/half), 0, 100) over the delta range
- dte:      clamp(100 * (1 - 0.5*|dte-center|/half), 0, 100) over the DTE range
- liquidity: 0.5*oi_score + 0.5*spread_score
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.core.decision_engine.contract import (
    COVERED_CALL,
    CSP,
    DecisionInput,
    SHARE_BUY,
)
from app.core.decision_engine.profiles import StrategyProfile

RETURN_WEIGHT = 0.40
DELTA_WEIGHT = 0.25
DTE_WEIGHT = 0.15
LIQUIDITY_WEIGHT = 0.20

_REGIME_BUY_SCORE = {"BULL": 100.0, "NEUTRAL": 50.0, "VOLATILE": 20.0, "BEAR": 0.0}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _return_component(return_pct: float, min_return_pct: float) -> float:
    if min_return_pct <= 0:
        return 100.0 if return_pct > 0 else 0.0
    return _clamp((return_pct / min_return_pct) * 40.0, 0.0, 100.0)


def _range_component(value: float, lo: float, hi: float) -> float:
    center = (lo + hi) / 2.0
    half = (hi - lo) / 2.0
    if half <= 0:
        return 100.0 if value == center else 0.0
    frac = abs(value - center) / half
    return _clamp(100.0 * (1.0 - 0.5 * frac), 0.0, 100.0)


def _liquidity_component(open_interest: int, spread_pct: float, profile: StrategyProfile) -> float:
    req = profile.liquidity
    oi_denom = max(req.min_open_interest * 4, 1)
    oi_score = _clamp(open_interest / oi_denom * 100.0, 0.0, 100.0)
    max_spread = req.max_bid_ask_spread_pct if req.max_bid_ask_spread_pct > 0 else 1.0
    spread_score = _clamp((max_spread - spread_pct) / max_spread * 100.0, 0.0, 100.0)
    return 0.5 * oi_score + 0.5 * spread_score


@dataclass(frozen=True)
class StrategyEval:
    """Strategy-specific evaluation (pre-sizing)."""

    passed_strategy_rules: bool
    score: float
    return_pct: Optional[float]
    soft_reasons: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    positive_reasons: List[str] = field(default_factory=list)


def _evaluate_option(inp: DecisionInput, profile: StrategyProfile, *, is_csp: bool) -> StrategyEval:
    c = inp.contract
    if c is None or c.strike is None or inp.price is None:
        return StrategyEval(False, 0.0, None, soft_reasons=["MISSING_CONTRACT"])

    delta_range = profile.csp_delta_range if is_csp else profile.cc_delta_range
    base = c.strike if is_csp else inp.price
    return_pct = round((c.premium / base) * 100.0, 4) if base else 0.0

    soft: List[str] = []
    pos: List[str] = []
    abs_delta = abs(c.delta)
    if not (delta_range[0] <= abs_delta <= delta_range[1]):
        soft.append("DELTA_OUT_OF_RANGE")
    else:
        pos.append("DELTA_IN_RANGE")
    if not (profile.dte_range[0] <= c.dte <= profile.dte_range[1]):
        soft.append("DTE_OUT_OF_RANGE")
    else:
        pos.append("DTE_IN_RANGE")
    if return_pct < profile.min_return_pct:
        soft.append("BELOW_RETURN_THRESHOLD")
    else:
        pos.append("MEETS_RETURN_THRESHOLD")

    ret_c = _return_component(return_pct, profile.min_return_pct)
    delta_c = _range_component(abs_delta, delta_range[0], delta_range[1])
    dte_c = _range_component(float(c.dte), profile.dte_range[0], profile.dte_range[1])
    liq_c = _liquidity_component(c.open_interest or 0, c.bid_ask_spread_pct if c.bid_ask_spread_pct is not None else 999.0, profile)
    score = round(
        RETURN_WEIGHT * ret_c + DELTA_WEIGHT * delta_c + DTE_WEIGHT * dte_c + LIQUIDITY_WEIGHT * liq_c,
        2,
    )

    risk: List[str] = []
    if inp.earnings_days is None and profile.earnings_blackout_days > 0:
        risk.append("EARNINGS_DATA_UNAVAILABLE")

    return StrategyEval(
        passed_strategy_rules=not soft,
        score=score,
        return_pct=return_pct,
        soft_reasons=soft,
        risk_flags=risk,
        positive_reasons=pos,
    )


def evaluate_csp(inp: DecisionInput, profile: StrategyProfile) -> StrategyEval:
    return _evaluate_option(inp, profile, is_csp=True)


def evaluate_covered_call(inp: DecisionInput, profile: StrategyProfile) -> StrategyEval:
    return _evaluate_option(inp, profile, is_csp=False)


def evaluate_share_buy(inp: DecisionInput, profile: StrategyProfile) -> StrategyEval:
    if inp.price is None:
        return StrategyEval(False, 0.0, None, soft_reasons=["MISSING_PRICE"])
    regime = (inp.market_regime or "").upper()
    regime_c = _REGIME_BUY_SCORE.get(regime, 0.0)
    risk: List[str] = []
    if inp.iv_rank is None:
        value_c = 50.0
        risk.append("IV_RANK_UNAVAILABLE")
    else:
        value_c = _clamp(100.0 - inp.iv_rank, 0.0, 100.0)
    score = round(0.6 * value_c + 0.4 * regime_c, 2)
    pos = ["SHARE_BUY_CANDIDATE"]
    return StrategyEval(
        passed_strategy_rules=True,
        score=score,
        return_pct=None,
        soft_reasons=[],
        risk_flags=risk,
        positive_reasons=pos,
    )


def evaluate_strategy(inp: DecisionInput, profile: StrategyProfile) -> StrategyEval:
    """Dispatch to the strategy-specific evaluator."""
    if inp.strategy == CSP:
        return evaluate_csp(inp, profile)
    if inp.strategy == COVERED_CALL:
        return evaluate_covered_call(inp, profile)
    if inp.strategy == SHARE_BUY:
        return evaluate_share_buy(inp, profile)
    return StrategyEval(False, 0.0, None, soft_reasons=[f"UNKNOWN_STRATEGY_{inp.strategy}"])
