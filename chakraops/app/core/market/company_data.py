# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2B: Minimal local company metadata for main universe symbols.
NO external paid APIs. Extend this dict as universe grows."""

from __future__ import annotations

from typing import Any, Dict, Optional

# Symbol -> { name, description?, sector?, industry? }
_COMPANY_META: Dict[str, Dict[str, Any]] = {
    "AAPL": {"name": "Apple Inc", "sector": "Technology", "industry": "Consumer Electronics"},
    "ABNB": {"name": "Airbnb Inc", "sector": "Consumer Cyclical", "industry": "Travel Services"},
    "AMD": {"name": "Advanced Micro Devices", "sector": "Technology", "industry": "Semiconductors"},
    "AMZN": {"name": "Amazon.com Inc", "sector": "Consumer Cyclical", "industry": "Internet Retail"},
    "AVGO": {"name": "Broadcom Inc", "sector": "Technology", "industry": "Semiconductors"},
    "COIN": {"name": "Coinbase Global", "sector": "Financial Services", "industry": "Financial Data & Stock Exchanges"},
    "COST": {"name": "Costco Wholesale", "sector": "Consumer Defensive", "industry": "Discount Stores"},
    "CRM": {"name": "Salesforce Inc", "sector": "Technology", "industry": "Software—Application"},
    "CRWD": {"name": "CrowdStrike Holdings", "sector": "Technology", "industry": "Software—Infrastructure"},
    "DIS": {"name": "Walt Disney Co", "sector": "Communication Services", "industry": "Entertainment"},
    "GOOGL": {"name": "Alphabet Inc (Google)", "sector": "Technology", "industry": "Internet Content & Information"},
    "HD": {"name": "Home Depot", "sector": "Consumer Cyclical", "industry": "Home Improvement Retail"},
    "JPM": {"name": "JPMorgan Chase", "sector": "Financial Services", "industry": "Banks—Diversified"},
    "META": {"name": "Meta Platforms", "sector": "Technology", "industry": "Internet Content & Information"},
    "MRVL": {"name": "Marvell Technology", "sector": "Technology", "industry": "Semiconductors"},
    "MSFT": {"name": "Microsoft Corp", "sector": "Technology", "industry": "Software—Infrastructure"},
    "MU": {"name": "Micron Technology", "sector": "Technology", "industry": "Semiconductors"},
    "NKE": {"name": "Nike Inc", "sector": "Consumer Cyclical", "industry": "Footwear & Accessories"},
    "NVDA": {"name": "NVIDIA Corp", "sector": "Technology", "industry": "Semiconductors"},
    "ORCL": {"name": "Oracle Corp", "sector": "Technology", "industry": "Software—Infrastructure"},
    "QQQ": {"name": "Invesco QQQ Trust", "sector": "Financial Services", "industry": "Asset Management"},
    "SNOW": {"name": "Snowflake Inc", "sector": "Technology", "industry": "Software—Infrastructure"},
    "SPY": {"name": "SPDR S&P 500 ETF", "sector": "Financial Services", "industry": "Asset Management"},
    "TSLA": {"name": "Tesla Inc", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers"},
    "TSM": {"name": "Taiwan Semiconductor", "sector": "Technology", "industry": "Semiconductors"},
    "WMT": {"name": "Walmart Inc", "sector": "Consumer Defensive", "industry": "Discount Stores"},
}


def get_company_metadata(symbol: str) -> Optional[Dict[str, Any]]:
    """Return company metadata for symbol, or None if not in local dict."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    data = _COMPANY_META.get(sym)
    if data is None:
        return None
    return {
        "symbol": sym,
        "name": data.get("name", sym),
        "description": data.get("description"),
        "sector": data.get("sector"),
        "industry": data.get("industry"),
    }
