# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Live market data adapter (Phase 8.2/8.3).

Selects provider: ThetaTerminalHttp -> YFinance -> SnapshotOnly.
Records active provider in LiveMarketData.data_source and errors list.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LiveMarketData:
    """Read-only live market data with freshness. All fields advisory."""

    data_source: str  # e.g. "ThetaTerminal", "yfinance (stocks-only)", "SNAPSHOT ONLY"
    last_update_utc: str  # ISO datetime
    underlying_prices: Dict[str, float] = field(default_factory=dict)
    option_chain_available: Dict[str, bool] = field(default_factory=dict)
    iv_by_contract: Dict[str, float] = field(default_factory=dict)
    greeks_by_contract: Dict[str, Dict[str, float]] = field(default_factory=dict)
    live_quotes: Dict[str, tuple] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


def _contract_key(symbol: str, strike: float, expiry: str, option_type: str) -> str:
    return f"{symbol}|{strike}|{expiry}|{option_type}"


def _select_provider(out_dir: Optional[Path] = None) -> tuple[object, str]:
    """Select first healthy provider: ThetaTerminal -> YFinance -> SnapshotOnly. Returns (provider, data_source_name)."""
    from app.market.providers import ThetaTerminalHttpProvider, YFinanceProvider, SnapshotOnlyProvider
    theta = ThetaTerminalHttpProvider()
    ok, detail = theta.health_check()
    if ok:
        return theta, "ThetaTerminal"
    logger.info("ThetaTerminal not used: %s", detail)
    try:
        yf = YFinanceProvider()
        ok, detail = yf.health_check()
        if ok:
            return yf, "yfinance (stocks-only)"
    except Exception as e:
        logger.info("YFinance not used: %s", e)
    snap = SnapshotOnlyProvider(out_dir=out_dir)
    snap.health_check()
    return snap, "SNAPSHOT ONLY (market closed / provider down)"


def fetch_live_market_data(
    symbols: List[str],
    out_dir: Optional[Path] = None,
) -> LiveMarketData:
    """Fetch live market data. Provider order: ThetaTerminal -> YFinance -> SnapshotOnly."""
    now_utc = datetime.now(timezone.utc).isoformat()
    symbols = [s for s in symbols if s and isinstance(s, str)]
    provider, data_source = _select_provider(out_dir)
    errors: List[str] = []
    underlying_prices = provider.fetch_underlying_prices(symbols)
    option_chain_available = provider.fetch_option_chain_availability(symbols)
    for s in symbols:
        if s not in option_chain_available:
            option_chain_available[s] = False
    if data_source == "SNAPSHOT ONLY (market closed / provider down)" and not underlying_prices:
        errors.append("No live or snapshot prices available; run pipeline to generate decision snapshot.")
    return LiveMarketData(
        data_source=data_source,
        last_update_utc=now_utc,
        underlying_prices=underlying_prices,
        option_chain_available=option_chain_available,
        iv_by_contract={},
        greeks_by_contract={},
        live_quotes={},
        errors=errors,
    )


__all__ = ["LiveMarketData", "fetch_live_market_data", "_contract_key", "_select_provider"]
