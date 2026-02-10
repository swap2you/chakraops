# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Canonical ChakraOps field map for ORATS Core Data v2.

Phase 8B: All downstream code must use canonical names only.
ORATS field names → ChakraOps canonical names. No duplicate mapping logic elsewhere.
"""

from __future__ import annotations

from typing import Any, Dict

# ORATS Core Data v2 (/datav2/cores) field names → ChakraOps canonical names
ORATS_TO_CANONICAL: Dict[str, str] = {
    # Volume
    "stkVolu": "stock_volume_today",
    "avgOptVolu20d": "avg_option_volume_20d",
    # IV
    "ivPctile1y": "iv_percentile_1y",
    "ivRank": "iv_rank",
    "ivRank1m": "iv_rank",  # alternate ORATS name
    "ivPct1m": "iv_rank",   # alternate
    # Price
    "pxCls": "last_close_price",
    "priorCls": "prior_close",
    "stockPrice": "last_close_price",  # from strikes/options if used
    # Date
    "tradeDate": "trade_date",
    "quoteDate": "quote_date",
    # Confidence / quality
    "confidence": "orats_confidence",
    # Fundamentals (when provided by cores)
    "sector": "sector",
    "marketCap": "market_cap",
    "industry": "industry",
}

# Canonical names that are required for EquitySnapshot (Phase 8E contract)
REQUIRED_CANONICAL_FIELDS = (
    "ticker",
    "trade_date",
    "last_close_price",
    "stock_volume_today",
)

# Optional canonical fields (do not block evaluation when missing)
OPTIONAL_CANONICAL_FIELDS = (
    "avg_stock_volume_20d",  # derived from hist/dailies when enabled
)

# Informational (never block; display when present)
INFORMATIONAL_CANONICAL_FIELDS = (
    "avg_option_volume_20d",
    "iv_percentile_1y",
    "iv_rank",
    "orats_confidence",
    "prior_close",
    "sector",
    "market_cap",
    "industry",
)


def orats_to_canonical(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map ORATS response keys to canonical ChakraOps names.
    Only includes keys present in raw; no inferred values. Preserves value types.
    """
    out: Dict[str, Any] = {}
    for orats_key, value in raw.items():
        if value is None:
            continue
        canonical = ORATS_TO_CANONICAL.get(orats_key)
        if canonical:
            out[canonical] = value
    return out
