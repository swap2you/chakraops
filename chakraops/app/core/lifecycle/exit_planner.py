# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.0: Hybrid Exit Model — dynamic premium extension (aggressive ride). Informational only."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.core.lifecycle.config import (
    DTE_HARD_EXIT_THRESHOLD,
    DTE_SOFT_EXIT_THRESHOLD,
    PANIC_ATR_MULT,
    PANIC_REGIME_FLIP_ENABLED,
    PREMIUM_BASE_TARGET_PCT,
    PREMIUM_EXTENSION_TARGET_PCT,
    STRUCTURE_EXTENSION_ENABLED,
)


def _parse_expiration(exp: Any) -> Optional[date]:
    """Parse exp from stage2 (iso string or date) to date."""
    if exp is None:
        return None
    if isinstance(exp, date):
        return exp if not isinstance(exp, datetime) else exp.date()
    if isinstance(exp, str):
        try:
            return datetime.strptime(exp[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def build_exit_plan(
    symbol: str,
    mode_decision: str,
    spot: Optional[float],
    eligibility_trace: Optional[Dict[str, Any]],
    stage2_trace: Optional[Dict[str, Any]],
    candles_meta: Optional[Dict[str, Any]],
    account_equity: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build exit plan dict (Hybrid Aggressive). Read-only from eligibility and stage2.
    Does not mutate mode_decision, score, tier, severity, sizing.
    """
    el = eligibility_trace or {}
    st2 = stage2_trace or {}
    spot_f = float(spot) if spot is not None else 0.0
    mode = (mode_decision or "NONE").strip().upper()
    missing: List[str] = []

    if mode not in ("CSP", "CC"):
        return {
            "enabled": False,
            "mode": mode,
            "premium_plan": None,
            "structure_plan": None,
            "time_plan": None,
            "panic_plan": None,
            "summary": {"style": "HYBRID_AGGRESSIVE", "primary_focus": "N/A", "what_to_watch": []},
            "inputs": {"symbol": symbol, "mode_decision": mode, "spot": spot},
            "missing_fields": ["mode_decision not CSP/CC"],
        }

    # Inputs snapshot (traceability)
    support_level = el.get("support_level")
    resistance_level = el.get("resistance_level")
    regime_daily = (el.get("regime") or "").strip().upper()
    regime_weekly = (el.get("regime_weekly") or "").strip().upper() if el.get("regime_weekly") else None
    computed = el.get("computed") or {}
    atr14 = computed.get("ATR14")
    sel = st2.get("selected_trade") if isinstance(st2, dict) else None
    exp = sel.get("exp") if isinstance(sel, dict) else None
    exp_date = _parse_expiration(exp)
    dte = sel.get("dte") if isinstance(sel, dict) else None
    if dte is None and exp_date is not None:
        dte = (exp_date - date.today()).days

    inputs = {
        "symbol": symbol,
        "mode_decision": mode,
        "spot": spot_f,
        "support_level": support_level,
        "resistance_level": resistance_level,
        "regime_daily": regime_daily or None,
        "regime_weekly": regime_weekly,
        "atr14": atr14,
        "expiration": exp_date.isoformat() if exp_date else None,
        "dte": dte,
    }

    # --- Premium plan (structure only; no real PnL) ---
    premium_plan: Dict[str, Any] = {
        "base_target_pct": PREMIUM_BASE_TARGET_PCT,
        "extension_target_pct": PREMIUM_EXTENSION_TARGET_PCT,
        "logic": "dynamic_extension",
        "states": {
            "early_capture": ">=60% and structure weak",
            "ride_zone": "60-75% and regime strong",
            "full_target": ">=75% or T2 reached",
        },
    }

    # --- Structure plan: T1, T2, T3, stop_hint ---
    structure_plan: Dict[str, Any] = {
        "T1": None,
        "T2": None,
        "T3": None,
        "stop_hint_price": None,
    }
    if spot_f <= 0:
        missing.append("spot")
    else:
        if mode == "CSP":
            # T1 = midpoint(spot, resistance), T2 = resistance, T3 = extension above resistance
            if resistance_level is not None:
                t1 = (spot_f + float(resistance_level)) / 2.0
                structure_plan["T1"] = round(t1, 4)
                structure_plan["T2"] = round(float(resistance_level), 4)
                if STRUCTURE_EXTENSION_ENABLED:
                    extension = float(resistance_level) - spot_f
                    structure_plan["T3"] = round(float(resistance_level) + extension, 4)
            else:
                missing.append("resistance_level")
            # Stop hint: support - ATR * PANIC_ATR_MULT
            if support_level is not None and atr14 is not None and atr14 > 0:
                stop = float(support_level) - atr14 * PANIC_ATR_MULT
                structure_plan["stop_hint_price"] = round(max(0.0, stop), 4)
            elif support_level is not None:
                structure_plan["stop_hint_price"] = round(float(support_level), 4)
        else:
            # CC: mirror — T1 = midpoint(spot, support), T2 = support, T3 extension below
            if support_level is not None:
                t1 = (spot_f + float(support_level)) / 2.0
                structure_plan["T1"] = round(t1, 4)
                structure_plan["T2"] = round(float(support_level), 4)
                if STRUCTURE_EXTENSION_ENABLED:
                    extension = spot_f - float(support_level)
                    structure_plan["T3"] = round(float(support_level) - extension, 4)
            else:
                missing.append("support_level")
            # Stop hint: resistance + ATR * PANIC_ATR_MULT
            if resistance_level is not None and atr14 is not None and atr14 > 0:
                stop = float(resistance_level) + atr14 * PANIC_ATR_MULT
                structure_plan["stop_hint_price"] = round(stop, 4)
            elif resistance_level is not None:
                structure_plan["stop_hint_price"] = round(float(resistance_level), 4)

    # Clamp T1/T2/T3/stop to non-negative where sensible (T3 can be above spot for CSP)
    for k in ("T1", "T2", "stop_hint_price"):
        v = structure_plan.get(k)
        if v is not None and v < 0:
            structure_plan[k] = 0.0
    if structure_plan.get("T3") is not None and mode == "CC" and structure_plan["T3"] < 0:
        structure_plan["T3"] = 0.0

    # --- Time plan ---
    time_plan: Dict[str, Any] = {
        "dte_soft_exit": DTE_SOFT_EXIT_THRESHOLD,
        "dte_hard_exit": DTE_HARD_EXIT_THRESHOLD,
        "dte": dte,
    }

    # --- Panic plan ---
    panic_flag = False
    panic_reason: Optional[str] = None
    if PANIC_REGIME_FLIP_ENABLED and mode == "CSP":
        if regime_daily != "UP":
            panic_flag = True
            panic_reason = "regime_flip"
        elif regime_weekly is not None and regime_weekly != "UP":
            panic_flag = True
            panic_reason = "regime_flip"
    if PANIC_REGIME_FLIP_ENABLED and mode == "CC":
        if regime_daily != "DOWN":
            panic_flag = True
            panic_reason = "regime_flip"
        elif regime_weekly is not None and regime_weekly != "DOWN":
            panic_flag = True
            panic_reason = "regime_flip"

    panic_plan: Dict[str, Any] = {
        "panic_flag": panic_flag,
        "panic_reason": panic_reason,
    }

    what_to_watch: List[str] = [
        "Premium toward 60% then 75%",
        "Price vs T1/T2 (and T3 if extension)",
        "DTE toward soft (14) and hard (7) exit",
    ]
    if panic_flag:
        what_to_watch.append("Regime flip — informational panic flag set")

    return {
        "enabled": True,
        "mode": mode,
        "premium_plan": premium_plan,
        "structure_plan": structure_plan,
        "time_plan": time_plan,
        "panic_plan": panic_plan,
        "summary": {
            "style": "HYBRID_AGGRESSIVE",
            "primary_focus": "ride_until_structure_or_75pct",
            "what_to_watch": what_to_watch,
        },
        "inputs": inputs,
        "missing_fields": missing,
    }
