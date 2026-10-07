# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.3: Shares eligibility (code-only reason_codes) and plan/sizing at request time. Not persisted."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from app.core.config.trade_rules import (
        SHARES_NEAR_SUPPORT_PCT,
        SHARES_RISK_PCT_DEFAULT,
        SHARES_ALLOW_REGIME_NEUTRAL,
        SHARES_ENTRY_ZONE_ATR_MULT,
        SHARES_STOP_ATR_MULT,
        SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS,
    )
except Exception:
    SHARES_NEAR_SUPPORT_PCT = 0.02
    SHARES_RISK_PCT_DEFAULT = 0.005
    SHARES_ALLOW_REGIME_NEUTRAL = False
    SHARES_ENTRY_ZONE_ATR_MULT = 0.25
    SHARES_STOP_ATR_MULT = 1.0
    SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS = ""


def _uat_force_eligible_symbols() -> List[str]:
    """UAT-only: symbols to force eligible (env overrides config). Read-time only."""
    raw = os.environ.get("SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS", "").strip() or SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS
    if not raw:
        return []
    return [s.strip().upper() for s in raw.split(",") if s.strip()]

try:
    from app.core.eligibility.config import CSP_RSI_MIN, CSP_RSI_MAX
except Exception:
    CSP_RSI_MIN, CSP_RSI_MAX = 40.0, 60.0


def compute_shares_eligibility(
    summary: Any,
    technicals: Dict[str, Any],
    symbol_eligibility: Dict[str, Any],
    mtf_levels: Optional[Dict[str, Any]] = None,
    symbol: str = "",
) -> Tuple[bool, List[str]]:
    """
    R23.3: Compute shares eligibility and code-only reason_codes.
    Returns (eligible, reason_codes). Not persisted.
    UAT-only: if symbol in SHARES_UAT_FORCE_ELIGIBLE_SYMBOLS (env or config), force eligible and add SHARES_UAT_FORCED.
    """
    reason_codes: List[str] = []
    # 1) Stock quality (Stage 1) pass
    stage1 = (getattr(summary, "stage1_status", None) or "").strip().upper()
    if stage1 != "PASS":
        reason_codes.append("NOT_STOCK_QUALITY")
    # 2) Regime preferred for shares (UP, or NEUTRAL if allowed)
    regime = (technicals.get("regime") or getattr(summary, "regime", None) or "").upper()
    if regime not in ("UP", "NEUTRAL", "SIDEWAYS"):
        reason_codes.append("REGIME_NOT_PREFERRED")
    elif regime in ("NEUTRAL", "SIDEWAYS") and not SHARES_ALLOW_REGIME_NEUTRAL:
        reason_codes.append("REGIME_NOT_PREFERRED")
    # 3) Near support: distance_to_support_pct <= SHARES_NEAR_SUPPORT_PCT
    spot_val = _float(technicals.get("spot") or technicals.get("support_level") or getattr(summary, "price", None))
    support_val = _float(technicals.get("support_level"))
    if mtf_levels:
        daily = mtf_levels.get("daily") if isinstance(mtf_levels.get("daily"), dict) else None
        weekly = mtf_levels.get("weekly") if isinstance(mtf_levels.get("weekly"), dict) else None
        if support_val is None and daily and daily.get("status_code") != "INSUFFICIENT_HISTORY":
            support_val = _float(daily.get("support"))
        if support_val is None and weekly and weekly.get("status_code") != "INSUFFICIENT_HISTORY":
            support_val = _float(weekly.get("support"))
    if spot_val is None or support_val is None or spot_val <= 0:
        reason_codes.append("NO_SUPPORT_OR_SPOT")
    else:
        distance_pct = abs(spot_val - support_val) / spot_val
        if distance_pct > SHARES_NEAR_SUPPORT_PCT:
            reason_codes.append("NOT_NEAR_SUPPORT")
    # 4) RSI within preferred range (or bypass if missing)
    rsi_val = _float(technicals.get("rsi"))
    if rsi_val is not None:
        if rsi_val < CSP_RSI_MIN or rsi_val > CSP_RSI_MAX:
            reason_codes.append("RSI_OUT_OF_RANGE")
    # 5) Data freshness OK
    prov = (getattr(summary, "provider_status", None) or "").strip().upper()
    if prov and prov not in ("OK", "PASS"):
        reason_codes.append("DATA_STALE")
    missing = symbol_eligibility.get("required_data_missing") or []
    if missing:
        reason_codes.append("DATA_STALE")
    eligible = len(reason_codes) == 0
    if eligible:
        reason_codes = ["SHARES_ELIGIBLE"]
    # UAT-only: force eligible for configured symbols (request-time only; does not affect persistence)
    force_list = _uat_force_eligible_symbols()
    sym_upper = (symbol or "").strip().upper()
    if sym_upper and sym_upper in force_list:
        eligible = True
        if "SHARES_UAT_FORCED" not in reason_codes:
            reason_codes = list(reason_codes) + ["SHARES_UAT_FORCED"]
    return eligible, reason_codes


def _float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_shares_plan_r233(
    summary: Any,
    technicals: Dict[str, Any],
    exit_plan: Dict[str, Any],
    hold_time_estimate: Optional[Dict[str, Any]],
    symbol: str,
    mtf_levels: Optional[Dict[str, Any]] = None,
    as_of_inputs: Optional[Dict[str, Any]] = None,
    symbol_eligibility: Optional[Dict[str, Any]] = None,
    account_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    R23.3: Build shares_plan object (request-time only). Not persisted.
    Includes eligible, reason_codes, spot, entry_zone (with basis), stop (with basis),
    targets (with basis), hold_time (sessions + method), sizing, as_of_inputs.
    """
    sel = symbol_eligibility or {}
    eligible, reason_codes = compute_shares_eligibility(summary, technicals, sel, mtf_levels, symbol=symbol)
    spot = _float(technicals.get("spot") or technicals.get("support_level") or getattr(summary, "price", None))
    if spot is None:
        spot = _float(technicals.get("resistance_level"))
    atr = _float(technicals.get("atr"))
    support = _float(technicals.get("support_level"))
    resistance = _float(technicals.get("resistance_level"))
    if mtf_levels:
        for tf in ("daily", "weekly"):
            blk = mtf_levels.get(tf) if isinstance(mtf_levels.get(tf), dict) else None
            if blk and blk.get("status_code") != "INSUFFICIENT_HISTORY":
                if support is None:
                    support = _float(blk.get("support"))
                if resistance is None:
                    resistance = _float(blk.get("resistance"))
    # Entry zone: around support; basis DAILY_SUPPORT | WEEKLY_SUPPORT | BOTH
    entry_basis = "DAILY_SUPPORT"
    if mtf_levels:
        daily_has = isinstance(mtf_levels.get("daily"), dict) and (mtf_levels["daily"].get("support") is not None)
        weekly_has = isinstance(mtf_levels.get("weekly"), dict) and (mtf_levels["weekly"].get("support") is not None)
        if daily_has and weekly_has:
            entry_basis = "BOTH"
        elif weekly_has:
            entry_basis = "WEEKLY_SUPPORT"
    ref = support if support is not None else spot
    zone_half = (atr * SHARES_ENTRY_ZONE_ATR_MULT) if atr and atr > 0 else (ref * 0.02 if ref else 0)
    if ref is not None:
        entry_low = round(ref - zone_half, 2) if zone_half else round(ref * 0.98, 2)
        entry_high = round(ref + zone_half, 2) if zone_half else round(ref * 1.02, 2)
        if entry_low is not None and entry_high is not None and entry_low > entry_high:
            entry_low, entry_high = entry_high, entry_low
    else:
        entry_low = entry_high = None
    # Stop: support minus ATR * mult; basis WEEKLY_SUPPORT_MINUS_ATR
    stop_price = None
    if support is not None and atr is not None and atr > 0:
        stop_price = round(support - atr * SHARES_STOP_ATR_MULT, 2)
    elif support is not None:
        stop_price = round(support * 0.97, 2)
    elif spot is not None:
        stop_price = round(spot * 0.95, 2)
    # Targets: t1, t2 from exit_plan; basis from resistance source
    t1 = _float(exit_plan.get("t1"))
    t2 = _float(exit_plan.get("t2"))
    targets_basis = "MIXED"
    if resistance is not None and t1 is not None and abs((t1 - resistance) / max(resistance, 1e-6)) < 0.01:
        targets_basis = "DAILY_RESISTANCE"
    if mtf_levels and isinstance(mtf_levels.get("weekly"), dict) and mtf_levels["weekly"].get("resistance") is not None:
        wr = _float(mtf_levels["weekly"].get("resistance"))
        if wr and t1 and abs((t1 - wr) / max(wr, 1e-6)) < 0.01:
            targets_basis = "WEEKLY_RESISTANCE"
    # Hold time
    hold_time = hold_time_estimate or {"sessions": 5, "basis_key": "default_estimate"}
    sessions_to_t1 = hold_time.get("sessions")
    method = (hold_time.get("basis_key") or "default_estimate").upper().replace("-", "_")
    if method == "ATR_SESSIONS_TO_TARGET":
        method = "ATR_DISTANCE"
    # Sizing
    sizing: Dict[str, Any] = {"suggested_shares": None, "suggested_cost": None, "max_loss": None, "risk_pct_used": None, "basis": "INSUFFICIENT_DATA"}
    if spot is not None and stop_price is not None and spot > stop_price:
        stop_dist = spot - stop_price
        account_value = None
        available_cash = None
        if account_summary:
            cash = _float(account_summary.get("cash"))
            buying_power = _float(account_summary.get("buying_power"))
            if cash is not None and buying_power is not None:
                available_cash = buying_power if buying_power > 0 else cash
                account_value = buying_power + cash
            if account_summary.get("total_capital") is not None:
                account_value = _float(account_summary.get("total_capital")) or account_value
        if account_value is not None and account_value > 0 and stop_dist > 0:
            risk_budget = account_value * SHARES_RISK_PCT_DEFAULT
            suggested_shares = int(risk_budget / stop_dist)
            if suggested_shares < 0:
                suggested_shares = 0
            suggested_cost = suggested_shares * spot
            if available_cash is not None and suggested_cost > available_cash and available_cash > 0:
                suggested_shares = int(available_cash / spot)
                suggested_cost = suggested_shares * spot
            max_loss = suggested_shares * stop_dist
            risk_pct_used = (max_loss / account_value) if account_value else None
            sizing = {
                "suggested_shares": suggested_shares,
                "suggested_cost": round(suggested_cost, 2),
                "max_loss": round(max_loss, 2),
                "risk_pct_used": round(risk_pct_used, 4) if risk_pct_used is not None else None,
                "basis": "ACCOUNT_RISK",
            }
    as_of = as_of_inputs or {}
    return {
        "eligible": eligible,
        "reason_codes": reason_codes,
        "spot": round(spot, 2) if spot is not None else None,
        "entry_zone": {
            "low": entry_low,
            "high": entry_high,
            "basis": entry_basis,
        },
        "stop": {"price": stop_price, "basis": "WEEKLY_SUPPORT_MINUS_ATR"} if stop_price is not None else {"price": None, "basis": "WEEKLY_SUPPORT_MINUS_ATR"},
        "targets": {"t1": t1, "t2": t2, "basis": targets_basis},
        "hold_time": {"sessions_to_t1": sessions_to_t1, "sessions_to_t2": None, "method": method},
        "sizing": sizing,
        "as_of_inputs": {
            "run_id": as_of.get("evaluation_run_id") or as_of.get("run_id"),
            "quote_as_of": as_of.get("quote_as_of"),
            "candles_as_of": as_of.get("candles_as_of"),
            "snapshot_used": as_of.get("snapshot_id"),
            "config_hash": as_of.get("config_hash"),
        },
    }
