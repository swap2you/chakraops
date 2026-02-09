# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Stop/target checks for journal trades. Used by nightly job to generate alerts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.core.journal.store import list_trades, get_trade

logger = logging.getLogger(__name__)


@dataclass
class TradeAlert:
    """Alert generated when stop or target is breached."""
    trade_id: str
    symbol: str
    alert_type: str  # STOP_BREACHED, TARGET_HIT
    message: str
    level: Optional[float] = None
    current_price: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)


def get_latest_price(symbol: str) -> Optional[float]:
    """Get latest price for symbol (ORATS or cached). Returns None if unavailable."""
    try:
        from app.core.data.orats_client import get_orats_live_summaries
        summaries = get_orats_live_summaries(symbol)
        if summaries and len(summaries) > 0:
            p = summaries[0].get("stockPrice")
            if p is not None:
                return float(p)
    except Exception as e:
        logger.debug("[JOURNAL_ALERTS] Price fetch failed for %s: %s", symbol, e)
    return None


def check_stops_and_targets(
    price_provider: Optional[Callable[[str], Optional[float]]] = None,
) -> List[TradeAlert]:
    """
    Check all open trades (remaining_qty > 0) for stop/target breaches.
    price_provider(symbol) -> float | None. Defaults to get_latest_price.
    """
    get_price = price_provider or get_latest_price
    alerts: List[TradeAlert] = []
    
    trades = list_trades(limit=200)
    for t in trades:
        if t.remaining_qty <= 0:
            continue
        price = get_price(t.symbol)
        if price is None:
            continue
        
        # Stop: for short options, stop_level is typically above current (e.g. stop loss on premium)
        if t.stop_level is not None:
            # Breach: price went against us. For sold option, stop might be "if underlying > X" or "if option mark > Y"
            # Interpret: if stop_level is set, breach when price >= stop_level (e.g. option mark hit stop)
            if price >= t.stop_level:
                alerts.append(TradeAlert(
                    trade_id=t.trade_id,
                    symbol=t.symbol,
                    alert_type="STOP_BREACHED",
                    message=f"Stop breached for {t.symbol} trade_id={t.trade_id} (price={price:.2f} >= stop={t.stop_level})",
                    level=t.stop_level,
                    current_price=price,
                    meta={"strategy": t.strategy, "strike": t.strike},
                ))
        
        # Targets: take-profit levels (e.g. option mark down to target)
        if t.target_levels:
            for level in t.target_levels:
                # Target hit: price <= target (we sold, want to buy back cheaper)
                if price <= level:
                    alerts.append(TradeAlert(
                        trade_id=t.trade_id,
                        symbol=t.symbol,
                        alert_type="TARGET_HIT",
                        message=f"Target hit for {t.symbol} trade_id={t.trade_id} (price={price:.2f} <= target={level})",
                        level=level,
                        current_price=price,
                        meta={"strategy": t.strategy, "strike": t.strike},
                    ))
                    break  # one alert per trade for targets
    
    return alerts
