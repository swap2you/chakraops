# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 7: Market Regime Engine (Index-Based Truth).

First-class Market Regime gates all evaluations. Uses SPY and QQQ daily data
(EMA20, EMA50, RSI(14)) to compute RISK_ON, NEUTRAL, or RISK_OFF.
Persistence: one record per trading day in out/market/market_regime.json.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Index symbols for regime computation
REGIME_INDEX_SYMBOLS = ("SPY", "QQQ")


class MarketRegime(str, Enum):
    """Market regime derived from index (SPY/QQQ) technicals."""
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"


@dataclass
class IndexInputs:
    """Per-index inputs used for regime calculation."""
    close: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    rsi: Optional[float] = None
    atr14: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "close": self.close,
            "ema20": self.ema20,
            "ema50": self.ema50,
            "rsi": self.rsi,
            "atr14": self.atr14,
        }


@dataclass
class MarketRegimeSnapshot:
    """Persistence shape: date, regime, and inputs per index."""
    date: str  # YYYY-MM-DD
    regime: str  # MarketRegime value
    inputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "regime": self.regime,
            "inputs": self.inputs,
        }


def _get_market_dir() -> Path:
    """Return out/market directory."""
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "market"


def _regime_path() -> Path:
    """Path to market_regime.json."""
    d = _get_market_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "market_regime.json"


def _compute_regime_from_inputs(inputs: Dict[str, IndexInputs]) -> MarketRegime:
    """
    Apply deterministic rules:
    - RISK_ON: EMA20 > EMA50 on BOTH SPY and QQQ, and RSI >= 45 (both)
    - RISK_OFF: EMA20 < EMA50 on EITHER index, or RSI <= 40 (either)
    - Else → NEUTRAL
    """
    spy = inputs.get("SPY") or IndexInputs()
    qqq = inputs.get("QQQ") or IndexInputs()

    def _ema20_above_50(idx: IndexInputs) -> Optional[bool]:
        if idx.ema20 is not None and idx.ema50 is not None:
            return idx.ema20 > idx.ema50
        return None

    def _rsi_ge_45(idx: IndexInputs) -> Optional[bool]:
        if idx.rsi is not None:
            return idx.rsi >= 45
        return None

    def _rsi_le_40(idx: IndexInputs) -> Optional[bool]:
        if idx.rsi is not None:
            return idx.rsi <= 40
        return None

    spy_above = _ema20_above_50(spy)
    qqq_above = _ema20_above_50(qqq)
    spy_rsi_ok = _rsi_ge_45(spy)
    qqq_rsi_ok = _rsi_ge_45(qqq)
    spy_rsi_off = _rsi_le_40(spy)
    qqq_rsi_off = _rsi_le_40(qqq)

    # RISK_OFF: EMA20 < EMA50 on either, or RSI <= 40 on either
    if spy_above is False or qqq_above is False:
        return MarketRegime.RISK_OFF
    if spy_rsi_off is True or qqq_rsi_off is True:
        return MarketRegime.RISK_OFF

    # RISK_ON: EMA20 > EMA50 on both, and RSI >= 45 (both)
    if spy_above is True and qqq_above is True:
        if (spy_rsi_ok is True and qqq_rsi_ok is True):
            return MarketRegime.RISK_ON
        if spy_rsi_ok is False or qqq_rsi_ok is False:
            # RSI not high enough for RISK_ON
            pass

    return MarketRegime.NEUTRAL


def _fetch_index_inputs(
    daily_provider: Optional[Any] = None,
) -> Dict[str, IndexInputs]:
    """Fetch EOD snapshot for SPY and QQQ; return as IndexInputs per symbol."""
    from app.core.journal.eod_snapshot import get_eod_snapshot
    result: Dict[str, IndexInputs] = {}
    for sym in REGIME_INDEX_SYMBOLS:
        try:
            snap = get_eod_snapshot(sym, daily_provider=daily_provider)
            result[sym] = IndexInputs(
                close=snap.close,
                ema20=snap.ema20,
                ema50=snap.ema50,
                rsi=snap.rsi,
                atr14=snap.atr14,
            )
        except Exception as e:
            logger.warning("[MARKET_REGIME] Failed to fetch %s: %s", sym, e)
            result[sym] = IndexInputs()
    return result


def compute_and_persist_regime(
    as_of_date: Optional[date] = None,
    daily_provider: Optional[Any] = None,
) -> MarketRegimeSnapshot:
    """
    Compute market regime from SPY/QQQ, persist to out/market/market_regime.json,
    return snapshot. Uses as_of_date for persistence key (default today UTC).
    """
    as_of_date = as_of_date or date.today()
    date_str = as_of_date.isoformat()
    inputs_dict = _fetch_index_inputs(daily_provider)
    inputs_typed: Dict[str, IndexInputs] = {}
    for k, v in inputs_dict.items():
        if isinstance(v, IndexInputs):
            inputs_typed[k] = v
        else:
            inputs_typed[k] = IndexInputs(
                close=v.get("close"),
                ema20=v.get("ema20"),
                ema50=v.get("ema50"),
                rsi=v.get("rsi"),
                atr14=v.get("atr14"),
            )
    regime = _compute_regime_from_inputs(inputs_typed)
    inputs_serializable = {k: v.to_dict() for k, v in inputs_typed.items()}
    snapshot = MarketRegimeSnapshot(date=date_str, regime=regime.value, inputs=inputs_serializable)
    path = _regime_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, indent=2)
        logger.info("[MARKET_REGIME] Persisted %s regime=%s", date_str, regime.value)
    except Exception as e:
        logger.exception("[MARKET_REGIME] Failed to persist: %s", e)
    return snapshot


def get_market_regime(
    as_of_date: Optional[date] = None,
    daily_provider: Optional[Any] = None,
    force_refresh: bool = False,
) -> MarketRegimeSnapshot:
    """
    Read regime for the given date from persistence. If not found or force_refresh,
    compute and persist. Returns snapshot with date, regime, inputs.
    """
    as_of_date = as_of_date or date.today()
    date_str = as_of_date.isoformat()
    path = _regime_path()

    if not force_refresh and path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("date") == date_str:
                return MarketRegimeSnapshot(
                    date=data.get("date", date_str),
                    regime=data.get("regime", MarketRegime.NEUTRAL.value),
                    inputs=data.get("inputs") or {},
                )
        except Exception as e:
            logger.warning("[MARKET_REGIME] Read failed: %s", e)

    return compute_and_persist_regime(as_of_date=as_of_date, daily_provider=daily_provider)


def get_regime_for_evaluation() -> str:
    """
    Return current market regime value (RISK_ON, NEUTRAL, RISK_OFF) for use in
    universe evaluation. Computes and persists if needed for today.
    """
    snapshot = get_market_regime()
    return snapshot.regime
