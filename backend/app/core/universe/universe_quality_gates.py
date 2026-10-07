# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 9.0: Universe quality gates — liquidity/tradeability hygiene.

Pure evaluation module. Does not fetch data. Never mutates anything.
Evaluates provided core_snapshot, chain_liquidity, data_sufficiency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GateDecision:
    """Result of universe quality gate evaluation."""
    symbol: str
    status: str  # "PASS" | "SKIP"
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


def _float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def evaluate_universe_quality(
    symbol: str,
    core_snapshot: Optional[Dict[str, Any]],
    chain_liquidity: Optional[Dict[str, Any]],
    data_sufficiency: Optional[Dict[str, Any]],
    gate_config: Dict[str, Any],
    symbol_override: Optional[Dict[str, Any]] = None,
) -> GateDecision:
    """
    Evaluate universe quality gates. Cheap-first. Does not fetch data.

    Returns GateDecision with status PASS or SKIP and reasons.
    """
    sym = (symbol or "").strip().upper()
    metrics: Dict[str, Any] = {}
    reasons: List[str] = []

    # Merge symbol override into config
    cfg = dict(gate_config or {})
    if symbol_override:
        for k, v in symbol_override.items():
            if v is not None:
                cfg[k] = v

    # A) Gates disabled globally or per symbol
    enabled = cfg.get("enabled", True)
    if not enabled:
        return GateDecision(symbol=sym, status="PASS", reasons=[], metrics={"gates_disabled": True})

    # B) Data sufficiency / staleness
    required_missing = (data_sufficiency or {}).get("required_data_missing") or []
    required_stale = (data_sufficiency or {}).get("required_data_stale") or []
    stale_days_block = int(cfg.get("data_stale_days_block") or 2)

    if required_missing:
        reasons.append("required_data_missing")
        metrics["missing_fields_count"] = len(required_missing)
        metrics["missing_fields"] = required_missing
        return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

    if required_stale:
        # required_data_stale non-empty means data exceeded block threshold (caller uses data_stale_days_block)
        reasons.append("stale_data")
        stale_days = (data_sufficiency or {}).get("stale_days")
        if stale_days is not None:
            metrics["stale_days"] = stale_days
        return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

    # C) Underlying price check
    snapshot = core_snapshot or {}
    price = _float(snapshot.get("price") or snapshot.get("stockPrice") or snapshot.get("stkPx"))
    if price is None:
        reasons.append("missing_price")
        return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

    metrics["price"] = price
    min_price = _float(cfg.get("min_price_usd")) or 8.0
    if price < min_price:
        reasons.append("price_below_min")
        metrics["min_price_usd"] = min_price
        return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

    max_price = _float(cfg.get("max_price_usd"))
    if max_price is not None and max_price > 0 and price > max_price:
        reasons.append("price_above_max")
        metrics["max_price_usd"] = max_price
        return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

    # D) Underlying spread check
    bid = _float(snapshot.get("bid"))
    ask = _float(snapshot.get("ask"))
    if bid is not None and ask is not None and bid > 0:
        mid = (bid + ask) / 2.0
        if mid > 0:
            spread_pct = (ask - bid) / mid
            metrics["spread_pct"] = spread_pct
            max_spread = _float(cfg.get("max_spread_pct")) or 0.012
            if spread_pct > max_spread:
                reasons.append("wide_spread")
                metrics["max_spread_pct"] = max_spread
                return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

    # E) Underlying avg volume check
    avg_vol = _int(snapshot.get("avg_stock_volume_20d")) or _int(snapshot.get("avg_volume"))
    if avg_vol is not None:
        metrics["avg_volume"] = avg_vol
        min_vol = _int(cfg.get("min_avg_volume")) or 800_000
        if avg_vol < min_vol:
            reasons.append("low_avg_volume")
            metrics["min_avg_volume"] = min_vol
            return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

    # F) Option liquidity check (only if chain_liquidity provided)
    chain = chain_liquidity or {}
    if chain:
        opt_bid = _float(chain.get("option_bid") or chain.get("bid"))
        opt_ask = _float(chain.get("option_ask") or chain.get("ask"))
        opt_mid = _float(chain.get("option_mid")) or (
            (opt_bid + opt_ask) / 2.0 if opt_bid is not None and opt_ask is not None else None
        )
        opt_oi = _int(chain.get("option_oi") or chain.get("open_interest"))
        opt_vol = _int(chain.get("option_volume") or chain.get("volume"))

        if opt_mid is not None and opt_mid <= 0:
            reasons.append("option_mid_invalid")
            return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

        if opt_mid is not None and opt_mid > 0 and opt_bid is not None and opt_ask is not None:
            opt_spread_pct = (opt_ask - opt_bid) / opt_mid
            metrics["option_spread_pct"] = opt_spread_pct
            max_opt = _float(cfg.get("max_option_bidask_pct")) or 0.10
            if opt_spread_pct > max_opt:
                reasons.append("wide_option_spread")
                metrics["max_option_bidask_pct"] = max_opt
                return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

        if opt_oi is not None:
            metrics["option_oi"] = opt_oi
            min_oi = _int(cfg.get("min_option_oi")) or 500
            if opt_oi < min_oi:
                reasons.append("low_oi")
                metrics["min_option_oi"] = min_oi
                return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

        if opt_vol is not None:
            metrics["option_volume"] = opt_vol
            min_vol_opt = _int(cfg.get("min_option_volume")) or 50
            if opt_vol < min_vol_opt:
                reasons.append("low_option_volume")
                metrics["min_option_volume"] = min_vol_opt
                return GateDecision(symbol=sym, status="SKIP", reasons=reasons, metrics=metrics)

    return GateDecision(symbol=sym, status="PASS", reasons=[], metrics=metrics)
