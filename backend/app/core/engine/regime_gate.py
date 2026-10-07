# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market regime gate: applies volatility kill switch before returning regime.

When volatility is high (VIX/SPY thresholds exceeded), overrides regime to Risk-Off
with reason 'volatility_spike'. Kept separate from existing risk_off logic so it
can be tested independently.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.core.risk.volatility_kill_switch import is_volatility_high
from app.core.settings import get_volatility_config


def _map_db_regime_to_risk(base_regime: Optional[str]) -> str:
    """Map DB regime (BULL/BEAR/NEUTRAL/UNKNOWN) to RISK_ON/RISK_OFF."""
    if base_regime is None:
        return "RISK_ON"
    u = (base_regime or "").upper()
    if u == "BULL":
        return "RISK_ON"
    if u == "BEAR":
        return "RISK_OFF"
    if u == "NEUTRAL":
        return "RISK_ON"
    return "RISK_OFF"  # UNKNOWN or anything else -> conservative


def evaluate_regime_gate(
    base_regime: Optional[str],
    volatility_config: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[str]]:
    """Evaluate regime with volatility kill switch; return (regime, reason).

    If is_volatility_high() is True, returns (RISK_OFF, "volatility_spike")
    regardless of base_regime. Otherwise returns (mapped_base_regime, None).

    Parameters
    ----------
    base_regime : Optional[str]
        Regime from DB: "BULL", "BEAR", "NEUTRAL", or "UNKNOWN". None if no regime.
    volatility_config : Optional[Dict[str, Any]]
        Config for is_volatility_high (vix_threshold, vix_change_pct, range_multiplier).
        If None, uses get_volatility_config().

    Returns
    -------
    Tuple[str, Optional[str]]
        (regime, reason). regime is "RISK_ON" or "RISK_OFF". reason is
        "volatility_spike" when kill switch triggered, else None.
    """
    config = volatility_config if volatility_config is not None else get_volatility_config()
    if is_volatility_high(config):
        return ("RISK_OFF", "volatility_spike")
    mapped = _map_db_regime_to_risk(base_regime)
    return (mapped, None)


__all__ = ["evaluate_regime_gate", "_map_db_regime_to_risk"]
