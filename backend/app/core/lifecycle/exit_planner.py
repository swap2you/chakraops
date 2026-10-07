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


def _first_valid_resistance(
    spot: float,
    resistances_by_tf: Dict[str, List[Dict[str, Any]]],
    min_distance_pct: float,
    eps_pct: float,
) -> tuple[Optional[float], Optional[str], Optional[float]]:
    """First resistance > spot*(1+eps) with distance_pct >= min_distance_pct. Returns (level, timeframe, distance_pct)."""
    for tf in ("daily", "weekly", "monthly"):
        for item in (resistances_by_tf.get(tf) or []):
            level = item.get("level")
            dist = item.get("distance_pct")
            if level is None or dist is None:
                continue
            if level <= spot * (1.0 + eps_pct):
                continue
            if dist < min_distance_pct:
                continue
            return (float(level), tf, float(dist))
    return (None, None, None)


def _first_valid_support(
    spot: float,
    supports_by_tf: Dict[str, List[Dict[str, Any]]],
    min_distance_pct: float,
    eps_pct: float,
) -> tuple[Optional[float], Optional[str], Optional[float]]:
    """First support < spot*(1-eps) with distance_pct >= min_distance_pct. Returns (level, timeframe, distance_pct)."""
    for tf in ("daily", "weekly", "monthly"):
        for item in (supports_by_tf.get(tf) or []):
            level = item.get("level")
            dist = item.get("distance_pct")
            if level is None or dist is None:
                continue
            if level >= spot * (1.0 - eps_pct):
                continue
            if dist < min_distance_pct:
                continue
            return (float(level), tf, float(dist))
    return (None, None, None)


def build_exit_plan_v235(
    spot: float,
    mode: str,
    atr: Optional[float],
    resistances_by_tf: Dict[str, List[Dict[str, Any]]],
    supports_by_tf: Dict[str, List[Dict[str, Any]]],
    min_distance_pct: float = 0.002,
    eps_pct: float = 0.001,
) -> Dict[str, Any]:
    """
    R23.4.5: Build structure plan with valid targets (monotonic T1 < T2 < T3) and S/R selection hardening.
    Uses first resistance/support beyond spot (by eps) and meeting min_distance_pct; else ATR fallback.
    """
    mode = (mode or "CSP").strip().upper()
    if mode not in ("CSP", "CC"):
        return {
            "structure_plan": {"T1": None, "T2": None, "T3": None, "stop_hint_price": None},
            "target_basis": "ATR_FALLBACK",
            "level_source_timeframe": None,
            "distance_to_t1_pct": None,
            "support_level": None,
            "resistance_level": None,
        }
    atr_f = float(atr) if atr is not None and atr > 0 else 0.0

    if mode == "CSP":
        res_level, res_tf, res_dist = _first_valid_resistance(
            spot, resistances_by_tf, min_distance_pct, eps_pct
        )
        sup_level, _, _ = _first_valid_support(spot, supports_by_tf, min_distance_pct, eps_pct)
        if res_level is not None and res_level > spot:
            t1 = (spot + res_level) / 2.0
            t2 = res_level
            t3 = res_level + (res_level - spot) if STRUCTURE_EXTENSION_ENABLED else res_level
            if t1 >= t2:
                t1, t2, t3 = spot + atr_f, spot + 2 * atr_f, spot + 3 * atr_f if atr_f else (t2, t2, t2)
                res_level, res_tf, res_dist = None, None, None
            else:
                t1, t2, t3 = round(t1, 4), round(t2, 4), round(t3, 4)
            dist_to_t1 = round((t1 - spot) / spot, 6) if spot and t1 else None
            target_basis = "SR_LEVEL" if res_level is not None else "ATR_FALLBACK"
            level_tf = res_tf
            distance_to_t1_pct = dist_to_t1
        else:
            if atr_f <= 0:
                t1 = t2 = t3 = spot
            else:
                t1, t2, t3 = round(spot + atr_f, 4), round(spot + 2 * atr_f, 4), round(spot + 3 * atr_f, 4)
            target_basis, level_tf, distance_to_t1_pct = "ATR_FALLBACK", None, round(atr_f / spot, 6) if spot else None
        stop = None
        if sup_level is not None and sup_level < spot:
            stop = sup_level - atr_f * PANIC_ATR_MULT if atr_f else sup_level
        elif atr_f:
            stop = spot - atr_f * PANIC_ATR_MULT
        stop = round(max(0.0, stop), 4) if stop is not None else None
        return {
            "structure_plan": {"T1": t1, "T2": t2, "T3": t3, "stop_hint_price": stop},
            "target_basis": target_basis,
            "level_source_timeframe": level_tf,
            "distance_to_t1_pct": distance_to_t1_pct,
            "support_level": round(sup_level, 4) if sup_level is not None else None,
            "resistance_level": round(res_level, 4) if res_level is not None else None,
        }
    # CC: targets below spot — require t1 > t2 > t3 (strictly decreasing)
    sup_level, sup_tf, sup_dist = _first_valid_support(spot, supports_by_tf, min_distance_pct, eps_pct)
    res_level, _, _ = _first_valid_resistance(spot, resistances_by_tf, min_distance_pct, eps_pct)
    if sup_level is not None and sup_level < spot:
        t1 = (spot + sup_level) / 2.0
        t2 = sup_level
        t3 = max(0.0, sup_level - (spot - sup_level)) if STRUCTURE_EXTENSION_ENABLED else sup_level
        if not (t1 > t2 > t3):
            t1 = spot - atr_f if atr_f else t2
            t2 = spot - 2 * atr_f if atr_f else t2
            t3 = max(0.0, spot - 3 * atr_f) if atr_f else t2
            sup_level, sup_tf, sup_dist = None, None, None
            level_tf = None
            distance_to_t1_pct = round(atr_f / spot, 6) if spot and atr_f else None
        else:
            t1, t2, t3 = round(t1, 4), round(t2, 4), round(t3, 4)
            dist_to_t1 = round((spot - t1) / spot, 6) if spot and t1 is not None else None
            level_tf = sup_tf
            distance_to_t1_pct = dist_to_t1
        target_basis = "SR_LEVEL" if sup_level is not None else "ATR_FALLBACK"
    else:
        if atr_f <= 0:
            t1 = t2 = t3 = spot
        else:
            t1, t2, t3 = round(spot - atr_f, 4), round(max(0.0, spot - 2 * atr_f), 4), round(max(0.0, spot - 3 * atr_f), 4)
        target_basis, level_tf = "ATR_FALLBACK", None
        distance_to_t1_pct = round(atr_f / spot, 6) if spot else None
    stop = None
    if res_level is not None and res_level > spot:
        stop = res_level + atr_f * PANIC_ATR_MULT if atr_f else res_level
    elif atr_f:
        stop = spot + atr_f * PANIC_ATR_MULT
    stop = round(stop, 4) if stop is not None else None
    return {
        "structure_plan": {"T1": t1, "T2": t2, "T3": t3, "stop_hint_price": stop},
        "target_basis": target_basis,
        "level_source_timeframe": level_tf,
        "distance_to_t1_pct": distance_to_t1_pct,
        "support_level": round(sup_level, 4) if sup_level is not None else None,
        "resistance_level": round(res_level, 4) if res_level is not None else None,
    }


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
