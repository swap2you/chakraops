# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.1: Position exit state evaluator. Deterministic; no broker calls."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.core.lifecycle.config import (
    DTE_HARD_EXIT_THRESHOLD,
    DTE_SOFT_EXIT_THRESHOLD,
    PREMIUM_BASE_TARGET_PCT,
    PREMIUM_EXTENSION_TARGET_PCT,
)

EXIT_HOLD = "HOLD"
EXIT_TAKE_PROFIT = "TAKE_PROFIT"
EXIT_NOW = "EXIT_NOW"
EXIT_ROLL_SUGGESTED = "ROLL_SUGGESTED"


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value if not isinstance(value, datetime) else value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _premium_capture_pct(entry_premium: float, bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """Premium captured so far: (entry - current_mid) / entry. Clamp [0, 1]. CSP and CC same formula."""
    if entry_premium <= 0 or bid is None or ask is None:
        return None
    current_mid = (float(bid) + float(ask)) / 2.0
    if current_mid >= entry_premium:
        return 0.0
    pct = (entry_premium - current_mid) / entry_premium
    return max(0.0, min(1.0, pct))


def evaluate_position(
    position: Dict[str, Any],
    current_spot: Optional[float],
    current_option_bid: Optional[float],
    current_option_ask: Optional[float],
    exit_plan_dict: Optional[Dict[str, Any]],
    today_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Evaluate one position against exit plan. Deterministic; does not mutate position.
    Returns evaluation dict with exit_signal, exit_reason, premium_capture_pct, etc.
    """
    if today_date is None:
        today_date = date.today()
    pos_id = position.get("position_id", "")
    symbol = (position.get("symbol") or "").strip().upper()
    mode = (position.get("mode") or "CSP").strip().upper()
    entry_premium = float(position.get("entry_premium") or 0)
    entry_date = _parse_date(position.get("entry_date"))
    exp_date = _parse_date(position.get("expiration"))

    # Data-missing path: no quote or bad entry_premium -> HOLD, no 0%
    if entry_premium <= 0:
        premium_capture_pct = None
        risk_flags_data: List[str] = ["BAD_ENTRY_PREMIUM"]
        exit_signal_data = EXIT_HOLD
        exit_reason_data = "data_missing"
    elif current_option_bid is None or current_option_ask is None:
        premium_capture_pct = None
        risk_flags_data = ["MISSING_OPTION_QUOTE"]
        exit_signal_data = EXIT_HOLD
        exit_reason_data = "data_missing"
    else:
        premium_capture_pct = _premium_capture_pct(entry_premium, current_option_bid, current_option_ask)
        risk_flags_data = []
        exit_signal_data = None
        exit_reason_data = None
    days_in_trade: Optional[int] = None
    if entry_date is not None:
        days_in_trade = (today_date - entry_date).days
    dte: Optional[int] = None
    if exp_date is not None:
        dte = (exp_date - today_date).days

    ep = exit_plan_dict or {}
    structure = ep.get("structure_plan") or {}
    time_plan = ep.get("time_plan") or {}
    panic_plan = ep.get("panic_plan") or {}
    inputs_plan = ep.get("inputs") or {}
    T1 = structure.get("T1")
    T2 = structure.get("T2")
    panic_flag = bool(panic_plan.get("panic_flag"))
    regime_daily = (inputs_plan.get("regime_daily") or "").strip().upper()
    spot_f = float(current_spot) if current_spot is not None else 0.0

    hit_T1 = False
    hit_T2 = False
    if T1 is not None and spot_f >= float(T1):
        hit_T1 = True
    if T2 is not None:
        if mode == "CSP" and spot_f >= float(T2):
            hit_T2 = True
        elif mode == "CC" and spot_f <= float(T2):
            hit_T2 = True

    regime_favorable = (mode == "CSP" and regime_daily == "UP") or (mode == "CC" and regime_daily == "DOWN")
    premium_75 = PREMIUM_EXTENSION_TARGET_PCT  # 0.75
    premium_60 = PREMIUM_BASE_TARGET_PCT       # 0.60
    premium_50 = 0.50
    dte_soft = time_plan.get("dte_soft_exit", DTE_SOFT_EXIT_THRESHOLD)
    dte_hard = time_plan.get("dte_hard_exit", DTE_HARD_EXIT_THRESHOLD)
    if dte is None:
        dte_for_rules = 999
    else:
        dte_for_rules = dte

    exit_signal = EXIT_HOLD
    exit_reason = "hold"
    risk_flags: List[str] = list(risk_flags_data)

    # Data missing: do not use premium in rules; return HOLD + data_missing
    if exit_signal_data is not None:
        out = {
            "position_id": pos_id,
            "symbol": symbol,
            "mode": mode,
            "premium_capture_pct": None,
            "days_in_trade": days_in_trade,
            "dte": dte,
            "hit_T1": hit_T1,
            "hit_T2": hit_T2,
            "exit_signal": exit_signal_data,
            "exit_reason": exit_reason_data,
            "risk_flags": risk_flags,
        }
        return out

    # Priority 1: Panic
    if panic_flag:
        exit_signal = EXIT_NOW
        exit_reason = "panic_regime_flip"
        risk_flags.append("panic")
    # Priority 2: Time hard (dte <= 7)
    elif dte_for_rules <= dte_hard:
        exit_signal = EXIT_NOW
        exit_reason = "dte_hard_exit"
        risk_flags.append("dte_hard")
    # Priority 3: Premium >= 75%
    elif premium_capture_pct is not None and premium_capture_pct >= premium_75:
        exit_signal = EXIT_NOW
        exit_reason = "premium_75_target"
    # Priority 4: Structure T2
    elif hit_T2:
        exit_signal = EXIT_NOW
        exit_reason = "structure_T2"
    # Priority 5: Time soft (dte <= 14)
    elif dte_for_rules <= dte_soft:
        exit_signal = EXIT_ROLL_SUGGESTED
        exit_reason = "dte_soft_roll"
        risk_flags.append("dte_soft")
    # Priority 6: T1 + premium 50%
    elif hit_T1 and premium_capture_pct is not None and premium_capture_pct >= premium_50:
        exit_signal = EXIT_TAKE_PROFIT
        exit_reason = "structure_T1_premium_50"
    # Priority 7: Premium 60% + structure/regime
    elif premium_capture_pct is not None and premium_capture_pct >= premium_60:
        if not hit_T2 and regime_favorable:
            exit_signal = EXIT_HOLD
            exit_reason = "ride_zone_60_regime_ok"
        else:
            exit_signal = EXIT_TAKE_PROFIT
            exit_reason = "premium_60_take_profit"
    # Default: HOLD
    else:
        exit_signal = EXIT_HOLD
        exit_reason = "hold"

    out = {
        "position_id": pos_id,
        "symbol": symbol,
        "mode": mode,
        "premium_capture_pct": premium_capture_pct,
        "days_in_trade": days_in_trade,
        "dte": dte,
        "hit_T1": hit_T1,
        "hit_T2": hit_T2,
        "exit_signal": exit_signal,
        "exit_reason": exit_reason,
        "risk_flags": risk_flags,
    }
    return out


def write_evaluation(evaluation: Dict[str, Any], base_dir: Union[str, Path] = "artifacts/positions/evaluations") -> Path:
    """Persist evaluation to base_dir/<position_id>.json. Creates parent dirs. Returns path written."""
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    pos_id = evaluation.get("position_id") or "unknown"
    path = base / f"{pos_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, indent=2, default=str)
    return path
