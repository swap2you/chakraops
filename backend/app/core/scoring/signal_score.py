# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.1: Signal score (diagnostic only). Never changes mode_decision or Stage-2."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.scoring.config import (
    ACCOUNT_EQUITY_DEFAULT,
    AFFORDABILITY_PCT_0,
    AFFORDABILITY_PCT_100,
    SCORE_WEIGHTS,
)
from app.core.eligibility.config import CSP_RSI_MIN, CSP_RSI_MAX, CC_RSI_MIN, CC_RSI_MAX, MAX_ATR_PCT


def _clamp100(x: float) -> float:
    return max(0.0, min(100.0, x))


def _safe_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def compute_signal_score(
    eligibility_trace: Optional[Dict[str, Any]],
    stage2_trace: Optional[Dict[str, Any]],
    spot: Optional[float],
    account_equity: float = ACCOUNT_EQUITY_DEFAULT,
) -> Dict[str, Any]:
    """
    Compute setup-quality and capital-practicality score from existing traces.
    Missing data degrades score and is recorded in missing_fields; never fails the run.
    """
    el = eligibility_trace or {}
    st2 = stage2_trace or {}
    missing: List[str] = []
    components: Dict[str, Any] = {}

    mode = (el.get("mode_decision") or "NONE").strip().upper()
    spot_val = float(spot) if spot is not None else None
    if spot_val is None:
        for candidate in (st2.get("spot_used"), el.get("close"), (el.get("computed") or {}).get("close")):
            if candidate is not None:
                try:
                    spot_val = float(candidate)
                    break
                except (TypeError, ValueError):
                    pass
    if spot_val is None:
        missing.append("spot")

    # --- regime_score (alignment already computed) ---
    regime = (el.get("regime") or "").strip().upper()
    if regime == "UP" and mode == "CSP":
        regime_score = 100.0
    elif regime == "DOWN" and mode == "CC":
        regime_score = 100.0
    elif regime in ("UP", "DOWN", "SIDEWAYS"):
        regime_score = 50.0  # neutral
    else:
        regime_score = 0.0
        if not regime:
            missing.append("regime")
    components["regime_score"] = regime_score

    # --- rsi_score (distance from ideal band midpoint) ---
    rsi_raw = el.get("rsi14")
    if rsi_raw is not None:
        try:
            rsi_val = float(rsi_raw)
            if mode == "CSP":
                mid = (CSP_RSI_MIN + CSP_RSI_MAX) / 2.0
                half_band = (CSP_RSI_MAX - CSP_RSI_MIN) / 2.0
            elif mode == "CC":
                mid = (CC_RSI_MIN + CC_RSI_MAX) / 2.0
                half_band = (CC_RSI_MAX - CC_RSI_MIN) / 2.0
            else:
                mid, half_band = 50.0, 10.0
            dist = abs(rsi_val - mid)
            if half_band <= 0:
                rsi_score = 100.0
            else:
                rsi_score = _clamp100(100.0 - (dist / half_band) * 50.0)
        except (TypeError, ValueError):
            rsi_score = 0.0
            missing.append("rsi14")
    else:
        rsi_score = 0.0
        missing.append("rsi14")
    components["rsi_score"] = rsi_score

    # --- sr_proximity_score (closer to relevant level = higher) ---
    dist_sup = el.get("distance_to_support_pct")
    dist_res = el.get("distance_to_resistance_pct")
    if mode == "CSP" and dist_sup is not None:
        try:
            d = float(dist_sup)
            # 0% distance = 100; 5%+ distance = lower
            sr_proximity_score = _clamp100(100.0 - d * 1000.0)  # 0.02 -> 80
        except (TypeError, ValueError):
            sr_proximity_score = 50.0
            missing.append("distance_to_support_pct")
    elif mode == "CC" and dist_res is not None:
        try:
            d = float(dist_res)
            sr_proximity_score = _clamp100(100.0 - d * 1000.0)
        except (TypeError, ValueError):
            sr_proximity_score = 50.0
            missing.append("distance_to_resistance_pct")
    else:
        sr_proximity_score = 50.0
        if mode in ("CSP", "CC"):
            missing.append("distance_to_support_pct" if mode == "CSP" else "distance_to_resistance_pct")
    components["sr_proximity_score"] = sr_proximity_score

    # --- vol_score (ATR_pct lower is better; above threshold -> 0) ---
    atr_pct = el.get("atr_pct")
    if atr_pct is not None:
        try:
            a = float(atr_pct)
            if a >= MAX_ATR_PCT:
                vol_score = 0.0
            else:
                vol_score = _clamp100(100.0 - (a / MAX_ATR_PCT) * 100.0)
        except (TypeError, ValueError):
            vol_score = 0.0
            missing.append("atr_pct")
    else:
        vol_score = 0.0
        missing.append("atr_pct")
    components["vol_score"] = vol_score

    # --- liquidity_score (from Stage-2 selected contract) ---
    sel = st2.get("selected_trade") if isinstance(st2, dict) else None
    if mode in ("CSP", "CC") and isinstance(sel, dict):
        spread_pct = sel.get("spread_pct")
        oi = sel.get("oi") or sel.get("open_interest")
        try:
            sp = float(spread_pct) if spread_pct is not None else 0.05
            sp = min(0.20, max(0.0, sp))
            liquidity_score = _clamp100(100.0 - sp * 500.0)  # 0.02 spread -> 90
        except (TypeError, ValueError):
            liquidity_score = 50.0
        if oi is not None:
            try:
                oi_val = int(oi)
                if oi_val >= 100:
                    liquidity_score = (liquidity_score + 100.0) / 2.0
                liquidity_score = _clamp100(liquidity_score)
            except (TypeError, ValueError):
                pass
    else:
        liquidity_score = None  # NONE or no selected_trade
    components["liquidity_score"] = liquidity_score

    # --- affordability_score ---
    notional_estimate = None
    notional_pct_of_account = None
    if spot_val is not None and spot_val > 0 and account_equity > 0:
        notional_estimate = spot_val * 100.0
        notional_pct_of_account = notional_estimate / account_equity
        if notional_pct_of_account <= AFFORDABILITY_PCT_100:
            affordability_score = 100.0
        elif notional_pct_of_account >= AFFORDABILITY_PCT_0:
            affordability_score = 0.0
        else:
            span = AFFORDABILITY_PCT_0 - AFFORDABILITY_PCT_100
            affordability_score = 100.0 - 100.0 * (notional_pct_of_account - AFFORDABILITY_PCT_100) / span
            affordability_score = _clamp100(affordability_score)
    else:
        affordability_score = 0.0
        if spot_val is None or spot_val <= 0:
            missing.append("spot")
    components["affordability_score"] = affordability_score

    # --- weighted composite ---
    w = SCORE_WEIGHTS
    key_to_component = {
        "regime": "regime_score",
        "rsi": "rsi_score",
        "sr_proximity": "sr_proximity_score",
        "vol": "vol_score",
        "liquidity": "liquidity_score",
        "affordability": "affordability_score",
    }
    composite = 0.0
    total_w = 0.0
    for key, weight in w.items():
        comp_key = key_to_component.get(key, f"{key}_score")
        val = components.get(comp_key)
        if val is None:
            continue
        try:
            composite += float(val) * weight
            total_w += weight
        except (TypeError, ValueError):
            pass
    # weighted sum (no renormalization when components missing)
    composite = _clamp100(composite)

    # Build result
    out: Dict[str, Any] = {
        "components": components,
        "composite_score": round(composite, 2),
        "notional_estimate": round(notional_estimate, 2) if notional_estimate is not None else None,
        "notional_pct_of_account": round(notional_pct_of_account, 6) if notional_pct_of_account is not None else None,
        "spread_pct_used": float(sel.get("spread_pct")) if isinstance(sel, dict) and sel.get("spread_pct") is not None else None,
        "oi_used": _safe_int(sel.get("oi") or sel.get("open_interest")) if isinstance(sel, dict) else None,
        "missing_fields": missing,
    }
    return out
