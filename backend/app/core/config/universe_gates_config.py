# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 9.0: Universe quality gates config — liquidity/tradeability hygiene.

Operator-tunable defaults. Per-symbol overrides via universe.json symbol_overrides.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name, "").lower().strip()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Defaults (operator-tunable via env)
GATES_ENABLED: bool = _bool_env("GATES_ENABLED", True)
GATE_MAX_SPREAD_PCT: float = _float_env("GATE_MAX_SPREAD_PCT", 0.012)  # 1.2%
GATE_MIN_PRICE_USD: float = _float_env("GATE_MIN_PRICE_USD", 8.0)
GATE_MAX_PRICE_USD: Optional[float] = _float_env("GATE_MAX_PRICE_USD", 600.0)  # 0 or negative to disable
GATE_MIN_AVG_VOLUME: int = _int_env("GATE_MIN_AVG_VOLUME", 800_000)
GATE_MIN_OPTION_OI: int = _int_env("GATE_MIN_OPTION_OI", 500)
GATE_MIN_OPTION_VOLUME: int = _int_env("GATE_MIN_OPTION_VOLUME", 50)
GATE_MAX_OPTION_BIDASK_PCT: float = _float_env("GATE_MAX_OPTION_BIDASK_PCT", 0.10)
GATE_DATA_STALE_DAYS_BLOCK: int = _int_env("GATE_DATA_STALE_DAYS_BLOCK", 2)
GATE_FAIL_MODE: str = os.getenv("GATE_FAIL_MODE", "SKIP")


def get_gate_config() -> Dict[str, Any]:
    """Return gate config dict for evaluate_universe_quality."""
    return {
        "enabled": GATES_ENABLED,
        "max_spread_pct": GATE_MAX_SPREAD_PCT,
        "min_price_usd": GATE_MIN_PRICE_USD,
        "max_price_usd": GATE_MAX_PRICE_USD,
        "min_avg_volume": GATE_MIN_AVG_VOLUME,
        "min_option_oi": GATE_MIN_OPTION_OI,
        "min_option_volume": GATE_MIN_OPTION_VOLUME,
        "max_option_bidask_pct": GATE_MAX_OPTION_BIDASK_PCT,
        "data_stale_days_block": GATE_DATA_STALE_DAYS_BLOCK,
        "fail_mode": GATE_FAIL_MODE,
    }


def resolve_gate_config_for_symbol(
    manifest: Dict[str, Any],
    symbol: str,
) -> Dict[str, Any]:
    """
    Merge global gate config with per-symbol overrides from manifest.
    symbol_overrides: { "TSLA": {"gates": {"max_option_bidask_pct": 0.12}}, "SMCI": {"gates": {"enabled": false}} }
    """
    cfg = get_gate_config().copy()
    overrides = manifest.get("symbol_overrides") or {}
    sym_key = (symbol or "").strip().upper()
    sym_ov = overrides.get(sym_key) if isinstance(overrides.get(sym_key), dict) else None
    if sym_ov:
        gates = sym_ov.get("gates")
        if isinstance(gates, dict):
            for k, v in gates.items():
                if v is not None:
                    cfg[k] = v
    return cfg


def get_symbol_gate_override(manifest: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
    """Return symbol_overrides[symbol].gates for gates module."""
    overrides = manifest.get("symbol_overrides") or {}
    sym_ov = overrides.get((symbol or "").strip().upper())
    if isinstance(sym_ov, dict):
        return sym_ov.get("gates") if isinstance(sym_ov.get("gates"), dict) else None
    return None
