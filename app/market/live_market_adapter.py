# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Live market data adapter (Phase 8.2).

Fetches live underlying price, option chain availability, and IV/Greeks (best effort).
Read-only, advisory only. Handles partial/missing data gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


@dataclass
class LiveMarketData:
    """Read-only live market data with freshness. All fields advisory."""

    data_source: str  # e.g. "ThetaTerminal" or "unavailable"
    last_update_utc: str  # ISO datetime
    underlying_prices: Dict[str, float] = field(default_factory=dict)  # symbol -> price
    option_chain_available: Dict[str, bool] = field(default_factory=dict)  # symbol -> available
    iv_by_contract: Dict[str, float] = field(default_factory=dict)  # key (symbol,strike,expiry,type) -> iv
    greeks_by_contract: Dict[str, Dict[str, float]] = field(default_factory=dict)  # key -> {delta, gamma, theta, vega}
    live_quotes: Dict[str, tuple] = field(default_factory=dict)  # key -> (bid, ask) best-effort
    errors: List[str] = field(default_factory=list)  # non-fatal errors / missing data reasons


def _contract_key(symbol: str, strike: float, expiry: str, option_type: str) -> str:
    return f"{symbol}|{strike}|{expiry}|{option_type}"


def fetch_live_market_data(symbols: List[str]) -> LiveMarketData:
    """Fetch live market data for given symbols. Graceful on partial/missing data.

    Args:
        symbols: List of underlying symbols to fetch (e.g. from snapshot).

    Returns:
        LiveMarketData with data_source, last_update_utc, and whatever could be fetched.
        underlying_prices, option_chain_available, iv_by_contract, greeks best-effort.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    underlying_prices: Dict[str, float] = {}
    option_chain_available: Dict[str, bool] = {}
    iv_by_contract: Dict[str, float] = {}
    greeks_by_contract: Dict[str, Dict[str, float]] = {}
    errors: List[str] = []

    provider = None
    try:
        from app.core.market_data.thetadata_provider import ThetaDataProvider
        provider = ThetaDataProvider()
    except Exception as e:
        errors.append(f"Live data provider unavailable: {e}")
        return LiveMarketData(
            data_source="unavailable",
            last_update_utc=now_utc,
            underlying_prices=underlying_prices,
            option_chain_available={s: False for s in symbols},
            iv_by_contract=iv_by_contract,
            greeks_by_contract=greeks_by_contract,
            live_quotes={},
            errors=errors,
        )

    data_source = "ThetaTerminal"

    for symbol in symbols:
        if not symbol or not isinstance(symbol, str):
            continue
        try:
            price = provider.get_underlying_price(symbol)
            if price and price > 0:
                underlying_prices[symbol] = float(price)
        except Exception as e:
            errors.append(f"{symbol} underlying price: {e}")

        try:
            # Option chain availability: best-effort (e.g. available dates for symbol)
            provider.get_available_dates(symbol, "trade")
            option_chain_available[symbol] = True
        except Exception as e:
            option_chain_available[symbol] = False
            errors.append(f"{symbol} chain/availability: {e}")

    # IV + Greeks: best effort (provider may not implement get_options_chain)
    for symbol in symbols:
        if not option_chain_available.get(symbol):
            continue
        try:
            chain = provider.get_options_chain(symbol)
            if chain:
                for opt in chain[:20]:
                    key = _contract_key(
                        getattr(opt, "symbol", symbol),
                        getattr(opt, "strike", 0),
                        getattr(opt, "expiry", ""),
                        getattr(opt, "option_type", "PUT"),
                    )
                    if getattr(opt, "iv", None) is not None:
                        iv_by_contract[key] = float(opt.iv)
                    g = {}
                    if getattr(opt, "delta", None) is not None:
                        g["delta"] = float(opt.delta)
                    if getattr(opt, "gamma", None) is not None:
                        g["gamma"] = float(opt.gamma)
                    if getattr(opt, "theta", None) is not None:
                        g["theta"] = float(opt.theta)
                    if getattr(opt, "vega", None) is not None:
                        g["vega"] = float(opt.vega)
                    if g:
                        greeks_by_contract[key] = g
        except NotImplementedError:
            pass
        except Exception as e:
            errors.append(f"{symbol} IV/Greeks: {e}")

    return LiveMarketData(
        data_source=data_source,
        last_update_utc=now_utc,
        underlying_prices=underlying_prices,
        option_chain_available=option_chain_available,
        iv_by_contract=iv_by_contract,
        greeks_by_contract=greeks_by_contract,
        live_quotes={},  # best-effort when provider supports per-contract quote
        errors=errors,
    )


__all__ = ["LiveMarketData", "fetch_live_market_data", "_contract_key"]
