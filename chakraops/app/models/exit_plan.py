# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Exit plan model: formal stop-loss, profit-take, time and regime-exit rules per position."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExitPlan:
    """Formal exit rules for an opened position.

    Stop logic uses option spread value (not just underlying price) where appropriate
    to account for gaps and bid/ask spreads.
    """

    profit_target_pct: float
    """Take profit when option value <= credit * (1 - profit_target_pct). E.g. 0.60 = close when 60% of credit retained."""

    max_loss_multiplier: float
    """Stop loss when option value >= credit * max_loss_multiplier. E.g. 2.0 = stop when spread value is 2× credit."""

    time_stop_days: int
    """Exit when DTE <= this (time-based exit)."""

    underlying_stop_breach: bool
    """If True, exit on first close beyond short strike (CSP: below strike; CC: above strike)."""


# Defaults per strategy (CSP, CC, BullPutSpread, BearCallSpread)
DEFAULT_PROFIT_TARGET_PCT = 0.60
DEFAULT_MAX_LOSS_MULTIPLIER = 2.0
DEFAULT_TIME_STOP_DAYS = 14


def get_default_exit_plan(strategy: str) -> ExitPlan:
    """Return the default ExitPlan for a strategy.

    - CSP, BullPutSpread: profit_target_pct=0.60, max_loss_multiplier=2.0,
      time_stop_days=14. CSP and BullPutSpread use underlying_stop_breach=True;
      BullPutSpread (as a spread) would use False—currently we treat CSP same as single put.
    - CC, BearCallSpread: same numeric defaults. CC uses underlying_stop_breach=True;
      BearCallSpread (spread) uses underlying_stop_breach=False.
    """
    strategy_upper = (strategy or "").strip().upper()
    # Spreads: no underlying breach exit (spread defines its own risk)
    underlying_breach = strategy_upper not in ("BULLPUTSPREAD", "BEARCALLSPREAD")
    return ExitPlan(
        profit_target_pct=DEFAULT_PROFIT_TARGET_PCT,
        max_loss_multiplier=DEFAULT_MAX_LOSS_MULTIPLIER,
        time_stop_days=DEFAULT_TIME_STOP_DAYS,
        underlying_stop_breach=underlying_breach,
    )


def exit_plan_to_dict(plan: Optional[ExitPlan]) -> Optional[dict]:
    """Serialize ExitPlan to a JSON-serializable dict."""
    if plan is None:
        return None
    return {
        "profit_target_pct": plan.profit_target_pct,
        "max_loss_multiplier": plan.max_loss_multiplier,
        "time_stop_days": plan.time_stop_days,
        "underlying_stop_breach": plan.underlying_stop_breach,
    }


def exit_plan_from_dict(data: Optional[dict]) -> Optional[ExitPlan]:
    """Deserialize ExitPlan from a dict (e.g. from JSON/DB)."""
    if not data:
        return None
    try:
        return ExitPlan(
            profit_target_pct=float(data.get("profit_target_pct", DEFAULT_PROFIT_TARGET_PCT)),
            max_loss_multiplier=float(data.get("max_loss_multiplier", DEFAULT_MAX_LOSS_MULTIPLIER)),
            time_stop_days=int(data.get("time_stop_days", DEFAULT_TIME_STOP_DAYS)),
            underlying_stop_breach=bool(data.get("underlying_stop_breach", True)),
        )
    except (TypeError, ValueError):
        return None
