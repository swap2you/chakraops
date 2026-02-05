# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""CSP/CC contract selection (Phase 5). Pure functions; snapshot-authoritative."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

# Snapshot context: price (underlying), iv_rank, regime, snapshot_age_minutes, etc.
SnapshotContext = Dict[str, Any]
# Config: DTE min/max, delta min/max, MAX_SPREAD_PCT, MIN_OI, MIN_VOLUME, MIN_ROC
OptionsConfig = Dict[str, Any]


@dataclass
class ContractResult:
    """Result of contract selection: eligible, rejection_reasons, chosen_contract, roc, dte, spread_pct, debug_inputs."""

    eligible: bool
    rejection_reasons: List[str] = field(default_factory=list)
    chosen_contract: Optional[Dict[str, Any]] = None
    roc: Optional[float] = None
    dte: Optional[int] = None
    spread_pct: Optional[float] = None
    debug_inputs: Dict[str, Any] = field(default_factory=dict)


def _default_config() -> OptionsConfig:
    from app.core.config.options_rules import (
        CSP_MIN_DTE, CSP_MAX_DTE, CSP_DELTA_MIN, CSP_DELTA_MAX, CSP_PROB_OTM_MIN,
        CC_MIN_DTE, CC_MAX_DTE, CC_DELTA_MIN, CC_DELTA_MAX, CC_PROB_OTM_MIN,
        MAX_SPREAD_PCT, MIN_OI, MIN_VOLUME, MIN_ROC,
    )
    return {
        "csp_min_dte": CSP_MIN_DTE,
        "csp_max_dte": CSP_MAX_DTE,
        "csp_delta_min": CSP_DELTA_MIN,
        "csp_delta_max": CSP_DELTA_MAX,
        "csp_prob_otm_min": CSP_PROB_OTM_MIN,
        "cc_min_dte": CC_MIN_DTE,
        "cc_max_dte": CC_MAX_DTE,
        "cc_delta_min": CC_DELTA_MIN,
        "cc_delta_max": CC_DELTA_MAX,
        "cc_prob_otm_min": CC_PROB_OTM_MIN,
        "max_spread_pct": MAX_SPREAD_PCT,
        "min_oi": MIN_OI,
        "min_volume": MIN_VOLUME,
        "min_roc": MIN_ROC,
    }


def _get(config: OptionsConfig, key: str, default: Any = None) -> Any:
    """Return config[key] if present, else default. Uses default when key is missing."""
    return (config or {}).get(key, default)


def select_csp_contract(
    symbol: str,
    snapshot_context: SnapshotContext,
    chain_provider: Any,
    config: Optional[OptionsConfig] = None,
) -> ContractResult:
    """Select one CSP (put) contract for symbol from snapshot context and chain.

    DTE window and delta band (puts: negative delta, config as absolute 0.15–0.30)
    are gated first. Liquidity: reject if bid/ask missing, mid<=0, spread_pct > MAX_SPREAD_PCT;
    if volume/open_interest exist and MIN_OI/MIN_VOLUME are set, enforce them (when absent, do not reject).
    Tie-breakers: closest to target delta; then nearer expiry; then higher strike (more OTM = more conservative).
    ROC = mid / strike (decimal).
    """
    cfg = config or _default_config()
    debug: Dict[str, Any] = {
        "symbol": symbol,
        "strategy": "CSP",
        "underlying_price": snapshot_context.get("price"),
        "iv_rank": snapshot_context.get("iv_rank"),
        "regime": snapshot_context.get("regime"),
    }
    min_dte = int(_get(cfg, "csp_min_dte", 30))
    max_dte = int(_get(cfg, "csp_max_dte", 45))
    delta_min_abs = float(_get(cfg, "csp_delta_min", 0.15))
    delta_max_abs = float(_get(cfg, "csp_delta_max", 0.25))
    min_prob_otm = float(_get(cfg, "csp_prob_otm_min", 0.70))
    max_spread_pct = float(_get(cfg, "max_spread_pct", 20.0))
    min_oi = int(_get(cfg, "min_oi", 0))
    min_volume = int(_get(cfg, "min_volume", 0))
    min_roc = float(_get(cfg, "min_roc", 0.005))
    price = snapshot_context.get("price")
    if price is None or price <= 0:
        return ContractResult(
            eligible=False,
            rejection_reasons=["options_skipped_no_price"],
            debug_inputs=debug,
        )
    # Backtest support: use as_of_date when provided, else date.today()
    _ao = snapshot_context.get("as_of_date")
    if _ao is not None:
        today = _ao if isinstance(_ao, date) else date.fromisoformat(str(_ao))
    else:
        today = date.today()
    try:
        expirations = chain_provider.get_expirations(symbol)
    except Exception:
        expirations = []
    if not expirations:
        return ContractResult(
            eligible=False,
            rejection_reasons=["chain_unavailable"],
            debug_inputs=debug,
        )
    in_dte = [e for e in expirations if min_dte <= (e - today).days <= max_dte]
    if not in_dte:
        return ContractResult(
            eligible=False,
            rejection_reasons=["no_expiry_in_dte_window"],
            debug_inputs={**debug, "min_dte": min_dte, "max_dte": max_dte, "expirations": [str(x) for x in expirations[:5]]},
        )
    # Puts: delta negative. Config is absolute 0.25–0.35 -> put delta in [-0.35, -0.25]
    put_delta_lo, put_delta_hi = -delta_max_abs, -delta_min_abs
    candidates: List[Dict[str, Any]] = []
    for exp in in_dte:
        try:
            chain = chain_provider.get_chain(symbol, exp, "P")
        except Exception:
            chain = []
        for row in chain:
            delta = row.get("delta")
            if delta is None:
                continue
            if not (put_delta_lo <= delta <= put_delta_hi):
                continue
            prob_otm = row.get("prob_otm")
            if prob_otm is not None and prob_otm < min_prob_otm:
                continue
            bid = row.get("bid")
            ask = row.get("ask")
            if bid is None and ask is None:
                continue
            bid = bid if bid is not None else 0.0
            ask = ask if ask is not None else 0.0
            mid = (bid + ask) / 2.0
            if mid <= 0:
                continue
            spread = ask - bid
            spread_pct = (spread / mid * 100.0) if mid else 999.0
            if spread_pct > max_spread_pct:
                continue
            oi = row.get("open_interest") or row.get("oi")
            vol = row.get("volume")
            if min_oi > 0 and (oi is None or int(oi) < min_oi):
                continue
            if min_volume > 0 and (vol is None or int(vol) < min_volume):
                continue
            strike = row.get("strike")
            if strike is None or strike <= 0:
                continue
            roc = mid / strike
            if roc < min_roc:
                continue
            dte = (exp - today).days
            # Tie-breaker: closest to target. Target = -csp_target_delta (e.g. -0.25 = slightly OTM).
            target_delta = -float(_get(cfg, "csp_target_delta", delta_min_abs) or delta_min_abs)
            candidates.append({
                "expiry": exp,
                "strike": strike,
                "right": "P",
                "delta": delta,
                "iv": row.get("iv"),
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "volume": vol,
                "open_interest": oi,
                "spread_pct": spread_pct,
                "roc": roc,
                "dte": dte,
                "_dist_delta": abs(delta - target_delta),
            })
    if not candidates:
        return ContractResult(
            eligible=False,
            rejection_reasons=["no_put_in_delta_range"],
            debug_inputs={**debug, "delta_range_abs": [delta_min_abs, delta_max_abs], "dte_window": [min_dte, max_dte]},
        )
    # Tie-break: closest to target delta, then nearer expiry, then higher strike (more conservative)
    candidates.sort(key=lambda c: (c["_dist_delta"], c["dte"], -c["strike"]))
    best = candidates[0]
    chosen = {
        "expiry": best["expiry"].isoformat() if hasattr(best["expiry"], "isoformat") else str(best["expiry"]),
        "strike": best["strike"],
        "right": "P",
        "delta": best["delta"],
        "prob_otm": best.get("prob_otm"),
        "iv_rank": best.get("iv_rank"),
        "iv": best.get("iv"),
        "bid": best["bid"],
        "ask": best["ask"],
        "mid": best["mid"],
        "volume": best.get("volume"),
        "open_interest": best.get("open_interest"),
    }
    return ContractResult(
        eligible=True,
        chosen_contract=chosen,
        roc=best["roc"],
        dte=best["dte"],
        spread_pct=best["spread_pct"],
        debug_inputs=debug,
    )


def select_cc_contract(
    symbol: str,
    snapshot_context: SnapshotContext,
    chain_provider: Any,
    config: Optional[OptionsConfig] = None,
    shares_held: int = 0,
) -> ContractResult:
    """Select one CC (call) contract for symbol. Requires shares_held > 0.

    Same DTE/delta/liquidity/ROC logic as CSP but for calls (positive delta).
    Tie-breakers: closest to target delta; then nearer expiry; then lower strike (more OTM = less assignment risk).
    ROC = mid / underlying_price (decimal). Documented: we use underlying price as denominator for consistency with “premium as % of share price”.
    """
    cfg = config or _default_config()
    debug: Dict[str, Any] = {
        "symbol": symbol,
        "strategy": "CC",
        "underlying_price": snapshot_context.get("price"),
        "iv_rank": snapshot_context.get("iv_rank"),
        "regime": snapshot_context.get("regime"),
        "shares_held": shares_held,
    }
    if shares_held <= 0:
        return ContractResult(
            eligible=False,
            rejection_reasons=["no_shares_held_for_cc"],
            debug_inputs=debug,
        )
    price = snapshot_context.get("price")
    if price is None or price <= 0:
        return ContractResult(
            eligible=False,
            rejection_reasons=["options_skipped_no_price"],
            debug_inputs=debug,
        )
    min_dte = int(_get(cfg, "cc_min_dte", 30))
    max_dte = int(_get(cfg, "cc_max_dte", 45))
    delta_min_abs = float(_get(cfg, "cc_delta_min", 0.15))
    delta_max_abs = float(_get(cfg, "cc_delta_max", 0.35))
    max_spread_pct = float(_get(cfg, "max_spread_pct", 20.0) or 20.0)
    min_oi = int(_get(cfg, "min_oi", 0) or 0)
    min_volume = int(_get(cfg, "min_volume", 0) or 0)
    min_roc = float(_get(cfg, "min_roc", 0.005) or 0.005)
    _ao = snapshot_context.get("as_of_date")
    if _ao is not None:
        today = _ao if isinstance(_ao, date) else date.fromisoformat(str(_ao))
    else:
        today = date.today()
    try:
        expirations = chain_provider.get_expirations(symbol)
    except Exception:
        expirations = []
    if not expirations:
        return ContractResult(
            eligible=False,
            rejection_reasons=["chain_unavailable"],
            debug_inputs=debug,
        )
    in_dte = [e for e in expirations if min_dte <= (e - today).days <= max_dte]
    if not in_dte:
        return ContractResult(
            eligible=False,
            rejection_reasons=["no_expiry_in_dte_window"],
            debug_inputs={**debug, "min_dte": min_dte, "max_dte": max_dte},
        )
    # Calls: delta positive; config 0.15–0.35
    call_delta_lo, call_delta_hi = delta_min_abs, delta_max_abs
    candidates = []
    for exp in in_dte:
        try:
            chain = chain_provider.get_chain(symbol, exp, "C")
        except Exception:
            chain = []
        for row in chain:
            delta = row.get("delta")
            if delta is None or not (call_delta_lo <= delta <= call_delta_hi):
                continue
            prob_otm = row.get("prob_otm")
            if prob_otm is not None and prob_otm < min_prob_otm:
                continue
            bid = row.get("bid")
            ask = row.get("ask")
            if bid is None and ask is None:
                continue
            bid = bid if bid is not None else 0.0
            ask = ask if ask is not None else 0.0
            mid = (bid + ask) / 2.0
            if mid <= 0:
                continue
            spread_pct = ((ask - bid) / mid * 100.0) if mid else 999.0
            if spread_pct > max_spread_pct:
                continue
            oi = row.get("open_interest") or row.get("oi")
            vol = row.get("volume")
            if min_oi > 0 and (oi is None or int(oi) < min_oi):
                continue
            if min_volume > 0 and (vol is None or int(vol) < min_volume):
                continue
            strike = row.get("strike")
            if strike is None or strike <= 0:
                continue
            roc = mid / price
            if roc < min_roc:
                continue
            dte = (exp - today).days
            target_delta = (call_delta_lo + call_delta_hi) / 2.0
            candidates.append({
                "expiry": exp,
                "strike": strike,
                "right": "C",
                "delta": delta,
                "iv": row.get("iv"),
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "volume": vol,
                "open_interest": oi,
                "spread_pct": spread_pct,
                "roc": roc,
                "dte": dte,
                "_dist_delta": abs(delta - target_delta),
            })
    if not candidates:
        return ContractResult(
            eligible=False,
            rejection_reasons=["no_call_in_delta_range"],
            debug_inputs={**debug, "delta_range": [call_delta_lo, call_delta_hi], "dte_window": [min_dte, max_dte]},
        )
    # Tie-break: closest to target delta, then nearer expiry, then lower strike (more OTM for CC = less assignment risk)
    candidates.sort(key=lambda c: (c["_dist_delta"], c["dte"], c["strike"]))
    best = candidates[0]
    chosen = {
        "expiry": best["expiry"].isoformat() if hasattr(best["expiry"], "isoformat") else str(best["expiry"]),
        "strike": best["strike"],
        "right": "C",
        "delta": best["delta"],
        "prob_otm": best.get("prob_otm"),
        "iv_rank": best.get("iv_rank"),
        "iv": best.get("iv"),
        "bid": best["bid"],
        "ask": best["ask"],
        "mid": best["mid"],
        "volume": best.get("volume"),
        "open_interest": best.get("open_interest"),
    }
    return ContractResult(
        eligible=True,
        chosen_contract=chosen,
        roc=best["roc"],
        dte=best["dte"],
        spread_pct=best["spread_pct"],
        debug_inputs=debug,
    )


__all__ = ["select_csp_contract", "select_cc_contract", "ContractResult", "SnapshotContext", "OptionsConfig"]
