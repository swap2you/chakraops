# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2: Curated stock universe + hard eligibility filters.

This module is intentionally *not* strategy logic.
- No CSP/CC logic
- No scoring/ranking
- No UI dependencies
- No symbol auto-discovery from Theta

Phase 2 responsibility:
- Own an authoritative, curated list of symbols
- Apply HARD, non-negotiable eligibility filters only
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from app.core.market.stock_models import StockSnapshot
from app.core.config.wheel_strategy_config import WHEEL_CONFIG, MIN_UNDERLYING_VOLUME
from app.data.stock_snapshot_provider import StockSnapshotProvider

_DEFAULT_MIN_AVG_STOCK_VOLUME: int = WHEEL_CONFIG[MIN_UNDERLYING_VOLUME]


@dataclass(frozen=True)
class UniverseSymbol:
    """Curated universe metadata (hardcoded for Phase 2)."""

    symbol: str
    has_options: bool = True
    is_etf: bool = False


class StockUniverseManager:
    """Owns curated universe and applies Phase-2 hard filters only."""

    def __init__(
        self,
        provider: StockSnapshotProvider,
        *,
        allow_etfs: bool = False,
        min_price: float = 20.0,
        max_price: float = 500.0,
        min_avg_stock_volume: int = _DEFAULT_MIN_AVG_STOCK_VOLUME,
        curated: Optional[List[UniverseSymbol]] = None,
        symbols_from_db: Optional[List[str]] = None,
    ) -> None:
        self._provider = provider
        self._allow_etfs = bool(allow_etfs)
        self._min_price = float(min_price)
        self._max_price = float(max_price)
        self._min_avg_stock_volume = int(min_avg_stock_volume)

        # When symbols_from_db is provided, use it as the authoritative list (no hardcoded universe).
        if symbols_from_db is not None and len(symbols_from_db) > 0:
            self._curated = [
                UniverseSymbol(s.strip().upper(), has_options=True, is_etf=False)
                for s in symbols_from_db
                if s and str(s).strip()
            ]
        elif curated is not None:
            self._curated = curated
        else:
            self._curated = [
                # Mega / large cap equities (options-listed)
                UniverseSymbol("AAPL"),
                UniverseSymbol("MSFT"),
                UniverseSymbol("AMZN"),
                UniverseSymbol("NVDA"),
                UniverseSymbol("META"),
                UniverseSymbol("GOOGL"),
                UniverseSymbol("TSLA"),
                UniverseSymbol("JPM"),
                UniverseSymbol("XOM"),
                UniverseSymbol("JNJ"),
                UniverseSymbol("UNH"),
                UniverseSymbol("V"),
                UniverseSymbol("MA"),
                UniverseSymbol("AVGO"),
                UniverseSymbol("COST"),
                UniverseSymbol("HD"),
                UniverseSymbol("WMT"),
                UniverseSymbol("LLY"),
                UniverseSymbol("NFLX"),
                UniverseSymbol("CRM"),
                # Common ETFs (present but excluded by default unless allow_etfs=True)
                UniverseSymbol("SPY", has_options=True, is_etf=True),
                UniverseSymbol("QQQ", has_options=True, is_etf=True),
            ]

        # Exclusion reasons from last `get_eligible_stocks()` run.
        self._last_exclusions: Dict[str, str] = {}

    def get_all_symbols(self) -> List[str]:
        return [u.symbol for u in self._curated]

    def explain_exclusion(self, symbol: str) -> str:
        """Return exclusion reason from the most recent run (or a default)."""
        sym = (symbol or "").upper()
        if not sym:
            return "invalid_symbol"
        return self._last_exclusions.get(sym, "not_evaluated_or_not_excluded")

    def get_eligible_stocks(self) -> List[StockSnapshot]:
        """Fetch snapshots and apply Phase-2 HARD filters.

        Rules:
        - price between $20 and $500 (if price available)
        - avg_stock_volume_20d >= min (if available)
        - has listed options == True
        - exclude ETFs unless explicitly allowed
        - exclude symbols with no valid snapshot response (provider returns None + reason)
        """

        self._last_exclusions = {}
        eligible: List[StockSnapshot] = []

        for u in self._curated:
            sym = u.symbol.upper()

            # Hard filter: options-listed required
            if not u.has_options:
                self._last_exclusions[sym] = "no_listed_options"
                continue

            # Hard filter: exclude ETFs unless allowed
            if u.is_etf and not self._allow_etfs:
                self._last_exclusions[sym] = "etf_excluded"
                continue

            snap, reason = self._provider.fetch_snapshot(sym, has_options=u.has_options)
            if snap is None:
                # Hard filter: exclude symbols with no valid snapshot response
                self._last_exclusions[sym] = reason or "no_valid_snapshot"
                continue

            # Hard filter: price between bounds (only if price is available)
            if snap.price is not None:
                if not (self._min_price <= float(snap.price) <= self._max_price):
                    self._last_exclusions[sym] = f"price_out_of_range({snap.price})"
                    continue

            # Hard filter: avg_stock_volume_20d threshold (only if available)
            avg_stock = getattr(snap, "avg_stock_volume_20d", None)
            if avg_stock is not None:
                if int(avg_stock) < self._min_avg_stock_volume:
                    self._last_exclusions[sym] = f"avg_stock_volume_below_threshold({avg_stock})"
                    continue

            eligible.append(snap)

        return eligible


__all__ = ["StockUniverseManager", "UniverseSymbol"]

