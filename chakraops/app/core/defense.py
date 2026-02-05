
#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Risk defense utilities for ChakraOps.

This module is intentionally conservative: it only produces *alerts* about
potential risk conditions. It does **not** auto-close trades or modify state.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


def check_market_stop(regime: str) -> bool:
    """Return True if a market-wide stop condition is triggered.

    Parameters
    ----------
    regime:
        Current market regime, e.g. ``"RISK_ON"`` or ``"RISK_OFF"``.

    Logic
    -----
    - Market stop triggers when regime is ``"RISK_OFF"``.
    """
    return regime.upper() == "RISK_OFF"


def check_position_stop(
    price_df: pd.DataFrame,
    support_level: float,
    atr: float,
    delta: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluate position-level stop conditions and return an alert if triggered.

    This function is *pure* and only inspects the provided data. It does not
    execute trades or persist any state. The caller is responsible for
    responding to the returned alert.

    Parameters
    ----------
    price_df:
        Daily OHLCV DataFrame with at least a ``close`` column. Must contain
        the most recent bar as the last row.
    support_level:
        Key support level for the position (e.g. recent swing low).
    atr:
        Average True Range value used to size the stop buffer.
    delta:
        Optional option delta for the short leg. If provided and greater than
        ``0.55`` (absolute risk increasing), a stop alert is triggered.

    Returns
    -------
    dict | None
        If a stop condition is met, returns a structured alert dictionary:

        .. code-block:: python

            {
                \"severity\": \"URGENT\",
                \"reason\": \"...text...\",
                \"conditions\": {
                    \"price_breach\": bool,
                    \"delta_breach\": bool,
                },
                \"metrics\": {
                    \"close\": float,
                    \"support_level\": float,
                    \"atr\": float,
                    \"stop_threshold\": float,
                    \"delta\": float | None,
                },
            }

        Otherwise returns ``None``.
    """
    if price_df is None or price_df.empty:
        return None

    latest = price_df.iloc[-1]
    close = float(latest.get("close", float("nan")))

    # Guard against invalid ATR/support values
    if atr is None or atr <= 0 or support_level is None:
        return None

    stop_threshold = support_level - 0.75 * atr

    price_breach = close < stop_threshold
    delta_breach = False

    if delta is not None:
        try:
            delta_val = float(delta)
            delta_breach = delta_val > 0.55
        except (TypeError, ValueError):
            delta_val = None
    else:
        delta_val = None

    if not (price_breach or delta_breach):
        return None

    reasons = []
    if price_breach:
        reasons.append(
            f"Price {close:.2f} breached stop {stop_threshold:.2f} "
            f"(support {support_level:.2f} - 0.75*ATR {atr:.2f})"
        )
    if delta_breach and delta_val is not None:
        reasons.append(f"Delta {delta_val:.2f} > 0.55 (gamma risk increasing)")

    reason_text = " | ".join(reasons) if reasons else "Stop condition triggered"

    return {
        "severity": "URGENT",
        "reason": reason_text,
        "conditions": {
            "price_breach": price_breach,
            "delta_breach": delta_breach,
        },
        "metrics": {
            "close": close,
            "support_level": float(support_level),
            "atr": float(atr),
            "stop_threshold": float(stop_threshold),
            "delta": delta_val,
        },
    }


__all__ = ["check_market_stop", "check_position_stop"]
