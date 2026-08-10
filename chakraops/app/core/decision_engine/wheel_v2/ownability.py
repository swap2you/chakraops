# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 ownability gate — would the operator want shares if assigned? Fail closed."""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Union

from app.core.decision_engine.contract import DecisionInput
from app.core.decision_engine.wheel_v2.contract import OwnabilityResult

# Regimes where owning shares after assignment is generally acceptable.
_OWNABLE_REGIMES = frozenset({"BULL", "NEUTRAL", "UP", "SIDEWAYS"})


def _g(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def evaluate_ownability(
    inp: Union[DecisionInput, Mapping[str, Any], Any],
    *,
    stage1_status: Optional[str] = None,
    quality_ok: Optional[bool] = None,
    liquidity_ok: Optional[bool] = None,
    earnings_blackout_days: int = 7,
) -> OwnabilityResult:
    """
    Evaluate whether assignment / share ownership is appropriate.

    Fail closed when critical inputs are missing (regime, stage1/quality, or price).
    Uses available proxies from DecisionInput or simple fields — no live ORATS.
    """
    missing: List[str] = []
    reasons: List[str] = []

    regime = (_g(inp, "market_regime") or _g(inp, "regime") or "").strip().upper()
    if not regime:
        missing.append("market_regime")

    stage1 = (
        (stage1_status or _g(inp, "stage1_status") or _g(inp, "stock_quality") or "")
        .strip()
        .upper()
    )
    q_ok = quality_ok
    if q_ok is None:
        if stage1:
            q_ok = stage1 in ("PASS", "OK", "ELIGIBLE")
        else:
            missing.append("stage1_status")

    price = _g(inp, "price")
    if price is None:
        missing.append("price")

    earnings_days = _g(inp, "earnings_days")
    # Earnings unknown is soft (reason) unless blackout is configured and we have days.
    if earnings_days is not None:
        try:
            ed = int(earnings_days)
            if ed >= 0 and ed <= int(earnings_blackout_days):
                reasons.append("EARNINGS_BLACKOUT")
        except (TypeError, ValueError):
            reasons.append("EARNINGS_UNKNOWN")

    liq = liquidity_ok
    if liq is None:
        # Optional proxy: contract OI when present; absence is not critical for ownability.
        contract = _g(inp, "contract")
        oi = _g(contract, "open_interest") if contract is not None else _g(inp, "open_interest")
        if oi is not None:
            try:
                liq = int(oi) > 0
            except (TypeError, ValueError):
                liq = None

    if missing:
        return OwnabilityResult(
            ownable=False,
            reason_codes=["OWNABILITY_MISSING_CRITICAL"] + missing,
            missing_critical=missing,
        )

    if q_ok is False:
        reasons.append("QUALITY_NOT_PASS")
    if regime and regime not in _OWNABLE_REGIMES:
        reasons.append("REGIME_NOT_OWNABLE")
    if liq is False:
        reasons.append("LIQUIDITY_WEAK")

    # Hard blockers: quality fail or bearish/volatile regime.
    hard = [r for r in reasons if r in ("QUALITY_NOT_PASS", "REGIME_NOT_OWNABLE", "EARNINGS_BLACKOUT")]
    ownable = len(hard) == 0
    if ownable:
        reasons = ["OWNABLE"] + [r for r in reasons if r not in hard]
    else:
        reasons = hard + [r for r in reasons if r not in hard]

    return OwnabilityResult(ownable=ownable, reason_codes=reasons, missing_critical=[])
