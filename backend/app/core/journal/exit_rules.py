# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Deterministic exit rules for CSP/CC. Input: Trade + EOD snapshot. Output: alerts with severity and recommended action."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.journal.eod_snapshot import EODSnapshot
from app.core.journal.models import Trade

logger = logging.getLogger(__name__)


@dataclass
class ExitRuleAlert:
    """Alert from exit-rules engine: severity and recommended action."""
    trade_id: str
    symbol: str
    rule_code: str  # STOP_BREACH, RISK_ALERT, PROFIT_T1, ROLL_ALERT, MANUAL_CHECK
    severity: str   # critical, warning, info
    message: str
    recommended_action: str
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "rule_code": self.rule_code,
            "severity": self.severity,
            "message": self.message,
            "recommended_action": self.recommended_action,
            "meta": self.meta,
        }


# ---------------------------------------------------------------------------
# CSP rules
# ---------------------------------------------------------------------------


def evaluate_csp_rules(trade: Trade, snapshot: EODSnapshot) -> List[ExitRuleAlert]:
    """
    CSP rules:
    - STOP_BREACH if close < EMA50 - 1.5*ATR14
    - RISK_ALERT if RSI < 35 and trending down (EMA20 < EMA50)
    - PROFIT_T1 if estimated premium decay 50% (use fill prices if available; else "manual check")
    """
    alerts: List[ExitRuleAlert] = []
    close = snapshot.close
    ema50 = snapshot.ema50
    ema20 = snapshot.ema20
    atr14 = snapshot.atr14
    rsi = snapshot.rsi

    # STOP_BREACH: close < EMA50 - 1.5*ATR14
    if close is not None and ema50 is not None and atr14 is not None and atr14 > 0:
        threshold = ema50 - 1.5 * atr14
        if close < threshold:
            alerts.append(ExitRuleAlert(
                trade_id=trade.trade_id,
                symbol=trade.symbol,
                rule_code="STOP_BREACH",
                severity="critical",
                message=f"CSP stop breach: {trade.symbol} close {close:.2f} < EMA50-1.5*ATR ({threshold:.2f})",
                recommended_action="Consider closing or adjusting position",
                meta={"close": close, "ema50": ema50, "atr14": atr14, "threshold": threshold},
            ))

    # RISK_ALERT: RSI < 35 and trending down (EMA20 < EMA50)
    if rsi is not None and ema20 is not None and ema50 is not None:
        if rsi < 35 and ema20 < ema50:
            alerts.append(ExitRuleAlert(
                trade_id=trade.trade_id,
                symbol=trade.symbol,
                rule_code="RISK_ALERT",
                severity="warning",
                message=f"CSP risk: {trade.symbol} RSI {rsi:.0f} < 35 and downtrend (EMA20 < EMA50)",
                recommended_action="Monitor; consider defensive action",
                meta={"rsi": rsi, "ema20": ema20, "ema50": ema50},
            ))

    # PROFIT_T1: 50% premium decay - use fill prices if available; else manual check
    has_50_target = trade.target_levels and 0.5 in trade.target_levels
    if has_50_target:
        if trade.avg_entry is not None and trade.avg_exit is None:
            # We have entry from fills but no exit yet; we don't have EOD option mark here
            alerts.append(ExitRuleAlert(
                trade_id=trade.trade_id,
                symbol=trade.symbol,
                rule_code="PROFIT_T1",
                severity="info",
                message="CSP 50% profit target: verify premium decay manually (no EOD option mark)",
                recommended_action="manual check",
                meta={"avg_entry": trade.avg_entry},
            ))
        else:
            alerts.append(ExitRuleAlert(
                trade_id=trade.trade_id,
                symbol=trade.symbol,
                rule_code="PROFIT_T1",
                severity="info",
                message="CSP 50% profit target set; check if premium decay ~50%",
                recommended_action="manual check",
                meta={},
            ))

    return alerts


# ---------------------------------------------------------------------------
# CC rules
# ---------------------------------------------------------------------------


def evaluate_cc_rules(trade: Trade, snapshot: EODSnapshot) -> List[ExitRuleAlert]:
    """
    CC rules:
    - ROLL_ALERT if close > strike - 0.5*ATR14
    """
    alerts: List[ExitRuleAlert] = []
    close = snapshot.close
    strike = trade.strike
    atr14 = snapshot.atr14

    if close is not None and strike is not None and atr14 is not None and atr14 > 0:
        roll_threshold = strike - 0.5 * atr14
        if close > roll_threshold:
            alerts.append(ExitRuleAlert(
                trade_id=trade.trade_id,
                symbol=trade.symbol,
                rule_code="ROLL_ALERT",
                severity="warning",
                message=f"CC roll alert: {trade.symbol} close {close:.2f} > strike-0.5*ATR ({roll_threshold:.2f})",
                recommended_action="Consider rolling covered call",
                meta={"close": close, "strike": strike, "atr14": atr14, "threshold": roll_threshold},
            ))

    return alerts


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def evaluate_exit_rules(trade: Trade, snapshot: EODSnapshot) -> List[ExitRuleAlert]:
    """Evaluate exit rules for a trade based on strategy. Returns list of alerts (may be empty)."""
    strategy_upper = (trade.strategy or "").upper()
    if strategy_upper == "CSP":
        return evaluate_csp_rules(trade, snapshot)
    if strategy_upper == "CC":
        return evaluate_cc_rules(trade, snapshot)
    return []


def best_action_from_alerts(alerts: List[ExitRuleAlert]) -> Optional[dict]:
    """
    From a list of exit-rule alerts, pick the single best recommended action for "next action".
    Priority: critical > warning > info. Returns dict with action, severity, message.
    """
    if not alerts:
        return None
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    best = min(alerts, key=lambda a: (severity_order.get(a.severity, 99), a.rule_code))
    return {
        "action": best.recommended_action,
        "severity": best.severity,
        "message": best.message,
        "rule_code": best.rule_code,
    }
