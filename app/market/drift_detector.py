# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Drift detector (Phase 8.2/8.3). Configurable thresholds; severity BLOCK/WARN/INFO."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.market.live_market_adapter import LiveMarketData, _contract_key


class DriftReason(str, Enum):
    """Reason code for detected drift (advisory only)."""
    PRICE_DRIFT = "PRICE_DRIFT"
    IV_DRIFT = "IV_DRIFT"
    CHAIN_UNAVAILABLE = "CHAIN_UNAVAILABLE"
    SPREAD_WIDENED = "SPREAD_WIDENED"


class DriftSeverity(str, Enum):
    """Severity for Slack/UI: BLOCK, WARN, INFO."""
    BLOCK = "BLOCK"
    WARN = "WARN"
    INFO = "INFO"


@dataclass
class DriftConfig:
    """Configurable drift thresholds (Phase 8.3)."""
    price_drift_warn_pct: float = 0.75
    iv_drift_abs: float = 0.03
    iv_drift_rel: float = 0.15
    spread_widened_mult: float = 1.5
    spread_mid_max: float = 0.20  # spread/mid > this => WARN


@dataclass
class DriftItem:
    """Single drift finding (advisory) with severity."""
    reason: DriftReason
    symbol: str
    message: str
    severity: DriftSeverity = DriftSeverity.INFO
    snapshot_value: Any = None
    live_value: Any = None


@dataclass
class DriftStatus:
    """Structured drift status (no actions). Read-only."""
    has_drift: bool
    items: List[DriftItem] = field(default_factory=list)


DEFAULT_DRIFT_CONFIG = DriftConfig()


def _severity_for_reason(reason: DriftReason) -> DriftSeverity:
    """CHAIN_UNAVAILABLE => BLOCK; SPREAD_WIDENED / IV_DRIFT => WARN; PRICE_DRIFT => INFO (caller may upgrade)."""
    if reason == DriftReason.CHAIN_UNAVAILABLE:
        return DriftSeverity.BLOCK
    if reason in (DriftReason.SPREAD_WIDENED, DriftReason.IV_DRIFT):
        return DriftSeverity.WARN
    return DriftSeverity.INFO


def _extract_symbols_from_snapshot(snapshot: Dict[str, Any]) -> List[str]:
    """Extract unique symbols from snapshot (selected_signals + candidates). No mutation."""
    symbols: List[str] = []
    seen: set = set()
    for item in (snapshot.get("selected_signals") or []) + (snapshot.get("scored_candidates") or [])[:50]:
        if not isinstance(item, dict):
            continue
        scored = item.get("scored", {})
        if not isinstance(scored, dict):
            continue
        cand = scored.get("candidate", {})
        if not isinstance(cand, dict):
            continue
        sym = cand.get("symbol")
        if sym and sym not in seen:
            seen.add(sym)
            symbols.append(sym)
    return symbols


def _extract_selected_assumptions(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract per-signal assumptions from selected_signals. No mutation."""
    out: List[Dict[str, Any]] = []
    for item in snapshot.get("selected_signals") or []:
        if not isinstance(item, dict):
            continue
        scored = item.get("scored", {})
        if not isinstance(scored, dict):
            continue
        cand = scored.get("candidate", {})
        if not isinstance(cand, dict):
            continue
        out.append({
            "symbol": cand.get("symbol"),
            "strike": cand.get("strike"),
            "expiry": cand.get("expiry"),
            "signal_type": cand.get("signal_type"),
            "option_right": cand.get("option_right", "PUT" if (cand.get("signal_type") == "CSP") else "CALL"),
            "underlying_price": cand.get("underlying_price"),
            "bid": cand.get("bid"),
            "ask": cand.get("ask"),
            "mid": cand.get("mid"),
            "iv": cand.get("iv"),
        })
    return out


def detect_drift(
    snapshot: Dict[str, Any],
    live: LiveMarketData,
    config: Optional[DriftConfig] = None,
) -> DriftStatus:
    """Compare snapshot vs live. Configurable thresholds; severity on each item. Does not mutate snapshot."""
    cfg = config or DEFAULT_DRIFT_CONFIG
    items: List[DriftItem] = []

    symbols = _extract_symbols_from_snapshot(snapshot)
    assumptions = _extract_selected_assumptions(snapshot)

    for sym in symbols:
        if not sym:
            continue
        if live.option_chain_available.get(sym) is False:
            items.append(DriftItem(
                reason=DriftReason.CHAIN_UNAVAILABLE,
                symbol=sym,
                message=f"Option chain unavailable for {sym}",
                severity=DriftSeverity.BLOCK,
            ))

    for a in assumptions:
        sym = a.get("symbol")
        if not sym:
            continue
        option_right = a.get("option_right") or ("PUT" if a.get("signal_type") == "CSP" else "CALL")

        # PRICE_DRIFT: INFO or WARN if above price_drift_warn_pct
        snapshot_underlying = a.get("underlying_price")
        if snapshot_underlying is not None and isinstance(snapshot_underlying, (int, float)):
            live_price = live.underlying_prices.get(sym)
            if live_price is not None and live_price > 0:
                pct = abs(float(live_price) - float(snapshot_underlying)) / float(snapshot_underlying) * 100.0
                if pct >= cfg.price_drift_warn_pct:
                    severity = DriftSeverity.WARN if pct >= cfg.price_drift_warn_pct * 2 else DriftSeverity.INFO
                    items.append(DriftItem(
                        reason=DriftReason.PRICE_DRIFT,
                        symbol=sym,
                        message=f"Underlying price drifted {pct:.1f}%",
                        severity=severity,
                        snapshot_value=snapshot_underlying,
                        live_value=live_price,
                    ))

        strike = a.get("strike")
        expiry = a.get("expiry")
        if strike is not None and expiry is not None:
            key = _contract_key(sym, float(strike), str(expiry), str(option_right))
            snapshot_iv = a.get("iv")
            live_iv = live.iv_by_contract.get(key)
            if snapshot_iv is not None and isinstance(snapshot_iv, (int, float)) and live_iv is not None:
                abs_d = abs(float(live_iv) - float(snapshot_iv))
                rel = abs_d / float(snapshot_iv) if float(snapshot_iv) != 0 else 0
                if abs_d >= cfg.iv_drift_abs or rel >= cfg.iv_drift_rel:
                    items.append(DriftItem(
                        reason=DriftReason.IV_DRIFT,
                        symbol=sym,
                        message=f"IV drifted for {expiry} ${strike} {option_right}",
                        severity=DriftSeverity.WARN,
                        snapshot_value=snapshot_iv,
                        live_value=live_iv,
                    ))

        bid, ask = a.get("bid"), a.get("ask")
        mid = a.get("mid")
        if bid is not None and ask is not None and isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and bid > 0:
            key = _contract_key(sym, float(a.get("strike", 0)), str(a.get("expiry", "")), str(option_right))
            live_quote = getattr(live, "live_quotes", None) or {}
            if isinstance(live_quote, dict) and key in live_quote:
                lb, la = live_quote[key]
                if lb is not None and la is not None and lb > 0:
                    snapshot_spread_pct = (float(ask) - float(bid)) / float(bid) * 100.0
                    live_spread_pct = (float(la) - float(lb)) / float(lb) * 100.0
                    mid_val = float(mid) if mid is not None and float(mid) > 0 else (float(bid) + float(ask)) / 2.0
                    spread_mid = (float(ask) - float(bid)) / mid_val if mid_val > 0 else 0
                    if live_spread_pct > snapshot_spread_pct * cfg.spread_widened_mult or spread_mid > cfg.spread_mid_max:
                        items.append(DriftItem(
                            reason=DriftReason.SPREAD_WIDENED,
                            symbol=sym,
                            message=f"Spread widened (snapshot {snapshot_spread_pct:.1f}% vs live {live_spread_pct:.1f}%)",
                            severity=DriftSeverity.WARN,
                            snapshot_value=snapshot_spread_pct,
                            live_value=live_spread_pct,
                        ))

    return DriftStatus(has_drift=len(items) > 0, items=items)


def drift_status_max_severity(status: DriftStatus) -> Optional[DriftSeverity]:
    """Return max severity among items (BLOCK > WARN > INFO), or None if no items."""
    if not status.items:
        return None
    order = {DriftSeverity.BLOCK: 3, DriftSeverity.WARN: 2, DriftSeverity.INFO: 1}
    return max(status.items, key=lambda i: order.get(i.severity, 0)).severity


__all__ = [
    "DriftReason",
    "DriftSeverity",
    "DriftConfig",
    "DriftItem",
    "DriftStatus",
    "detect_drift",
    "drift_status_max_severity",
    "DEFAULT_DRIFT_CONFIG",
]
