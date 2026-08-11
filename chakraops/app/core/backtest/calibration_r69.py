# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R69 regime labels + calibration proposal records (no auto-apply)."""

from __future__ import annotations

from typing import Any, Dict, List


REGIME_LABELS = (
    "2008_crisis",
    "2011_eu_stress",
    "2015_16",
    "2018_vol",
    "covid_2020",
    "2022_rates",
    "strong_bull",
    "low_volatility",
    "high_volatility",
)


def label_regime(period_start: str, period_end: str, *, proxy: bool = False) -> Dict[str, Any]:
    return {
        "period_start": period_start,
        "period_end": period_end,
        "proxy_index_regime": bool(proxy),
        "instrument_history_claim": None,
        "disclaimer": "Do not claim SPY/NVDA have 50–60 years of instrument history.",
        "manual_only": True,
    }


def propose_calibration_change(
    *,
    parameter: str,
    current_value: Any,
    proposed_value: Any,
    evidence_refs: List[str],
) -> Dict[str, Any]:
    return {
        "parameter": parameter,
        "current_value": current_value,
        "proposed_value": proposed_value,
        "evidence_refs": list(evidence_refs or []),
        "auto_applied": False,
        "requires_oos_acceptance": True,
        "manual_only": True,
        "trade_execution": False,
        "message": "Research proposal only — production thresholds require explicit acceptance.",
    }
