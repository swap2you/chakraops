# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Deterministic trade construction engine (Phase 4.1).

Converts SelectedSignal + OptionContext into TradeProposal or NO_TRADE (rejected).
No execution logic; no broker assumptions; risk-first always.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from app.models.trade_proposal import TradeProposal
from app.signals.models import SignalType
from app.signals.selection import SelectedSignal

# Optional for OptionContext (signals model may not depend on app.models at runtime)
try:
    from app.models.option_context import OptionContext
except ImportError:
    OptionContext = Any  # type: ignore[misc, assignment]


def build_trade(
    signal: SelectedSignal,
    option_context: Optional["OptionContext"],
    portfolio_config: Dict[str, Any],
) -> TradeProposal:
    """Build a TradeProposal from a selected signal and context, or return rejected proposal.

    Rules (risk-first; if any fails -> rejected=True with reason):

    CSP:
    - Strike must be BELOW expected_move_1sd distance (put strike <= underlying * (1 - expected_move_1sd)).
    - Credit >= 0.5% of notional.

    Credit Spreads (BullPutSpread, BearCallSpread):
    - Spread width from {1, 2, 5}; width chosen so max_loss <= portfolio max risk per trade.
    - Credit / max_loss >= 0.25.
    - Short strike must be outside expected move (put: below; call: above).

    Single-leg CC is treated as BearCallSpread with unbounded max_loss -> rejected.
    """
    candidate = signal.scored.candidate
    symbol = candidate.symbol
    expiry = candidate.expiry
    strike = candidate.strike
    underlying = candidate.underlying_price
    contracts = 1

    # Credit: premium per share * 100 * contracts
    mid = candidate.mid
    bid = candidate.bid
    premium_per_share = mid if mid is not None else bid
    if premium_per_share is None:
        premium_per_share = 0.0
    credit_estimate = premium_per_share * 100 * contracts

    expected_move_1sd: Optional[float] = None
    if option_context is not None and getattr(option_context, "expected_move_1sd", None) is not None:
        expected_move_1sd = option_context.expected_move_1sd

    if candidate.signal_type == SignalType.CSP:
        return _build_csp(
            symbol=symbol,
            expiry=expiry,
            strike=strike,
            underlying=underlying,
            contracts=contracts,
            credit_estimate=credit_estimate,
            expected_move_1sd=expected_move_1sd,
            portfolio_config=portfolio_config,
        )
    # CC -> BearCallSpread (single-leg treated as rejected)
    return _build_credit_spread(
        symbol=symbol,
        expiry=expiry,
        short_strike=strike,
        underlying=underlying,
        contracts=contracts,
        credit_estimate=credit_estimate,
        expected_move_1sd=expected_move_1sd,
        portfolio_config=portfolio_config,
        is_call=True,
    )


def _build_csp(
    symbol: str,
    expiry: date,
    strike: float,
    underlying: float,
    contracts: int,
    credit_estimate: float,
    expected_move_1sd: Optional[float],
    portfolio_config: Dict[str, Any],
) -> TradeProposal:
    """CSP: single put. Max loss = strike * 100 * contracts - credit."""
    notional = strike * 100 * contracts
    max_loss = notional - credit_estimate
    account_balance = float(portfolio_config.get("account_balance", 100_000.0))
    max_risk_pct = float(portfolio_config.get("max_risk_per_trade_pct", 1.0)) / 100.0
    risk_budget = max_risk_pct * account_balance
    # Strike must be BELOW expected move (put strike <= underlying * (1 - expected_move_1sd))
    if expected_move_1sd is None:
        return TradeProposal(
            symbol=symbol,
            strategy_type="CSP",
            expiry=expiry,
            strikes=strike,
            contracts=contracts,
            credit_estimate=credit_estimate,
            max_loss=max_loss,
            expected_move_1sd=None,
            distance_to_risk=None,
            risk_reward_ratio=(credit_estimate / max_loss) if max_loss > 0 else None,
            construction_reason="CSP",
            rejected=True,
            rejection_reason="expected_move_1sd required for CSP (risk-first)",
        )
    threshold_below = underlying * (1.0 - expected_move_1sd)
    if strike > threshold_below:
        return TradeProposal(
            symbol=symbol,
            strategy_type="CSP",
            expiry=expiry,
            strikes=strike,
            contracts=contracts,
            credit_estimate=credit_estimate,
            max_loss=max_loss,
            expected_move_1sd=expected_move_1sd,
            distance_to_risk=strike - threshold_below if threshold_below else None,
            risk_reward_ratio=(credit_estimate / max_loss) if max_loss > 0 else None,
            construction_reason="CSP",
            rejected=True,
            rejection_reason=f"CSP strike {strike} above 1sd threshold {threshold_below:.2f} (strike must be below expected move)",
        )
    # Credit >= 0.5% of notional
    min_credit = 0.005 * notional
    if credit_estimate < min_credit:
        return TradeProposal(
            symbol=symbol,
            strategy_type="CSP",
            expiry=expiry,
            strikes=strike,
            contracts=contracts,
            credit_estimate=credit_estimate,
            max_loss=max_loss,
            expected_move_1sd=expected_move_1sd,
            distance_to_risk=None,
            risk_reward_ratio=(credit_estimate / max_loss) if max_loss > 0 else None,
            construction_reason="CSP",
            rejected=True,
            rejection_reason=f"CSP credit {credit_estimate:.2f} below 0.5% notional ({min_credit:.2f})",
        )
    # Risk budget: max_loss <= portfolio max risk per trade
    if max_loss > risk_budget:
        return TradeProposal(
            symbol=symbol,
            strategy_type="CSP",
            expiry=expiry,
            strikes=strike,
            contracts=contracts,
            credit_estimate=credit_estimate,
            max_loss=max_loss,
            expected_move_1sd=expected_move_1sd,
            distance_to_risk=None,
            risk_reward_ratio=(credit_estimate / max_loss) if max_loss > 0 else None,
            construction_reason="CSP",
            rejected=True,
            rejection_reason=f"CSP max_loss {max_loss:.0f} exceeds risk budget {risk_budget:.0f} ({max_risk_pct*100}% of account)",
        )
    return TradeProposal(
        symbol=symbol,
        strategy_type="CSP",
        expiry=expiry,
        strikes=strike,
        contracts=contracts,
        credit_estimate=credit_estimate,
        max_loss=max_loss,
        expected_move_1sd=expected_move_1sd,
        distance_to_risk=None,
        risk_reward_ratio=(credit_estimate / max_loss) if max_loss > 0 else None,
        construction_reason="CSP",
        rejected=False,
        rejection_reason=None,
    )


def _build_credit_spread(
    symbol: str,
    expiry: date,
    short_strike: float,
    underlying: float,
    contracts: int,
    credit_estimate: float,
    expected_move_1sd: Optional[float],
    portfolio_config: Dict[str, Any],
    is_call: bool,
) -> TradeProposal:
    """Credit spread (BullPutSpread or BearCallSpread). Single-leg = unbounded max_loss -> reject."""
    # Single-leg: no long strike -> unbounded max loss for call; for put, max_loss = strike*100 - credit
    # Spec: "Spread width selected from {1, 2, 5}" -> we require a spread. Single-leg call = reject.
    strategy_type: str = "BearCallSpread" if is_call else "BullPutSpread"
    # Short strike must be outside expected move: put -> strike <= underlying*(1-em); call -> strike >= underlying*(1+em)
    if expected_move_1sd is None:
        return TradeProposal(
            symbol=symbol,
            strategy_type=strategy_type,
            expiry=expiry,
            strikes=(short_strike,),
            contracts=contracts,
            credit_estimate=credit_estimate,
            max_loss=float("inf") if is_call else (short_strike * 100 * contracts - credit_estimate),
            expected_move_1sd=None,
            distance_to_risk=None,
            risk_reward_ratio=None,
            construction_reason=strategy_type,
            rejected=True,
            rejection_reason="expected_move_1sd required for credit spread (risk-first)",
        )
    if is_call:
        threshold_above = underlying * (1.0 + expected_move_1sd)
        if short_strike < threshold_above:
            return TradeProposal(
                symbol=symbol,
                strategy_type=strategy_type,
                expiry=expiry,
                strikes=(short_strike,),
                contracts=contracts,
                credit_estimate=credit_estimate,
                max_loss=float("inf"),
                expected_move_1sd=expected_move_1sd,
                distance_to_risk=threshold_above - short_strike,
                risk_reward_ratio=None,
                construction_reason=strategy_type,
                rejected=True,
                rejection_reason=f"BearCallSpread short strike {short_strike} inside 1sd (must be >= {threshold_above:.2f})",
            )
        # Single-leg call has unbounded max_loss -> reject
        return TradeProposal(
            symbol=symbol,
            strategy_type=strategy_type,
            expiry=expiry,
            strikes=(short_strike,),
            contracts=contracts,
            credit_estimate=credit_estimate,
            max_loss=float("inf"),
            expected_move_1sd=expected_move_1sd,
            distance_to_risk=None,
            risk_reward_ratio=None,
            construction_reason=strategy_type,
            rejected=True,
            rejection_reason="single-leg BearCallSpread has unbounded max_loss; spread required",
        )
    # Put spread: short strike must be below expected move
    threshold_below = underlying * (1.0 - expected_move_1sd)
    if short_strike > threshold_below:
        return TradeProposal(
            symbol=symbol,
            strategy_type=strategy_type,
            expiry=expiry,
            strikes=(short_strike,),
            contracts=contracts,
            credit_estimate=credit_estimate,
            max_loss=short_strike * 100 * contracts - credit_estimate,
            expected_move_1sd=expected_move_1sd,
            distance_to_risk=short_strike - threshold_below,
            risk_reward_ratio=None,
            construction_reason=strategy_type,
            rejected=True,
            rejection_reason=f"BullPutSpread short strike {short_strike} above 1sd threshold {threshold_below:.2f}",
        )
    # Single-leg put spread not implemented (we'd need long strike for width)
    return TradeProposal(
        symbol=symbol,
        strategy_type=strategy_type,
        expiry=expiry,
        strikes=(short_strike,),
        contracts=contracts,
        credit_estimate=credit_estimate,
        max_loss=short_strike * 100 * contracts - credit_estimate,
        expected_move_1sd=expected_move_1sd,
        distance_to_risk=None,
        risk_reward_ratio=None,
        construction_reason=strategy_type,
        rejected=True,
        rejection_reason="single-leg BullPutSpread: spread width required for risk budget",
    )


# --- Iron Condor (Phase 4.2) ---

# Strategy gating: only allow IC when regime=RISK_ON, IV rank 30-70, expected move < 40% of total width
IC_IV_RANK_MIN = 30.0
IC_IV_RANK_MAX = 70.0
IC_EXPECTED_MOVE_PCT_OF_WIDTH_MAX = 0.40


def _iron_condor_gate(
    option_context: Optional["OptionContext"],
    total_width: float,
    underlying: float,
    regime: str,
) -> tuple[bool, Optional[str]]:
    """Return (allowed, rejection_reason). Only allow when RISK_ON, IV 30-70, expected move < 40% width."""
    if regime != "RISK_ON":
        return False, f"iron condor only in RISK_ON regime (current: {regime})"
    if option_context is None:
        return False, "option_context required for iron condor gating"
    iv_rank = getattr(option_context, "iv_rank", None)
    if iv_rank is not None:
        if iv_rank < IC_IV_RANK_MIN:
            return False, f"IV rank {iv_rank} below {IC_IV_RANK_MIN} (iron condor requires 30-70)"
        if iv_rank > IC_IV_RANK_MAX:
            return False, f"IV rank {iv_rank} above {IC_IV_RANK_MAX} (iron condor requires 30-70)"
    expected_move_1sd = getattr(option_context, "expected_move_1sd", None)
    if expected_move_1sd is None or total_width <= 0 or underlying <= 0:
        return False, "expected_move_1sd and width required for iron condor (risk-first)"
    expected_move_dollars = expected_move_1sd * underlying
    threshold = IC_EXPECTED_MOVE_PCT_OF_WIDTH_MAX * total_width
    if expected_move_dollars >= threshold:
        return False, f"expected move {expected_move_dollars:.2f} >= 40% of width ({threshold:.2f})"
    return True, None


def build_iron_condor_trade(
    ic_candidate: "IronCondorCandidate",
    option_context: Optional["OptionContext"],
    portfolio_config: Dict[str, Any],
    regime: str,
) -> TradeProposal:
    """Build a TradeProposal for an iron condor. Strategy gating: RISK_ON, IV 30-70, expected move < 40% width."""
    symbol = ic_candidate.symbol
    expiry = ic_candidate.expiry
    total_credit = ic_candidate.total_credit
    combined_max_loss = ic_candidate.combined_max_loss
    total_width = ic_candidate.total_width
    underlying = ic_candidate.underlying_price
    contracts = 1

    allowed, rejection = _iron_condor_gate(
        option_context, total_width, underlying, regime
    )
    if not allowed:
        return TradeProposal(
            symbol=symbol,
            strategy_type="IRON_CONDOR",
            expiry=expiry,
            strikes=(
                ic_candidate.put_short_strike,
                ic_candidate.put_long_strike,
                ic_candidate.call_short_strike,
                ic_candidate.call_long_strike,
            ),
            contracts=contracts,
            credit_estimate=total_credit,
            max_loss=combined_max_loss,
            expected_move_1sd=getattr(option_context, "expected_move_1sd", None) if option_context else None,
            distance_to_risk=None,
            risk_reward_ratio=(total_credit / combined_max_loss) if combined_max_loss > 0 else None,
            construction_reason="IRON_CONDOR",
            rejected=True,
            rejection_reason=rejection,
        )

    # Risk budget
    account_balance = float(portfolio_config.get("account_balance", 100_000.0))
    max_risk_pct = float(portfolio_config.get("max_risk_per_trade_pct", 1.0)) / 100.0
    risk_budget = max_risk_pct * account_balance
    if combined_max_loss > risk_budget:
        return TradeProposal(
            symbol=symbol,
            strategy_type="IRON_CONDOR",
            expiry=expiry,
            strikes=(
                ic_candidate.put_short_strike,
                ic_candidate.put_long_strike,
                ic_candidate.call_short_strike,
                ic_candidate.call_long_strike,
            ),
            contracts=contracts,
            credit_estimate=total_credit,
            max_loss=combined_max_loss,
            expected_move_1sd=getattr(option_context, "expected_move_1sd", None) if option_context else None,
            distance_to_risk=None,
            risk_reward_ratio=(total_credit / combined_max_loss) if combined_max_loss > 0 else None,
            construction_reason="IRON_CONDOR",
            rejected=True,
            rejection_reason=f"iron condor max_loss {combined_max_loss:.0f} exceeds risk budget {risk_budget:.0f}",
        )

    return TradeProposal(
        symbol=symbol,
        strategy_type="IRON_CONDOR",
        expiry=expiry,
        strikes=(
            ic_candidate.put_short_strike,
            ic_candidate.put_long_strike,
            ic_candidate.call_short_strike,
            ic_candidate.call_long_strike,
        ),
        contracts=contracts,
        credit_estimate=total_credit,
        max_loss=combined_max_loss,
        expected_move_1sd=getattr(option_context, "expected_move_1sd", None) if option_context else None,
        distance_to_risk=None,
        risk_reward_ratio=(total_credit / combined_max_loss) if combined_max_loss > 0 else None,
        construction_reason="IRON_CONDOR",
        rejected=False,
        rejection_reason=None,
    )


__all__ = ["build_trade", "build_iron_condor_trade", "_iron_condor_gate"]
