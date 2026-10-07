#!/usr/bin/env python3
"""Simple smoke test for regime detection."""

from __future__ import annotations

import json
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from app.core.regime import build_weekly_from_daily, compute_regime
from app.core.market_data.factory import get_market_data_provider


def main() -> int:
    """Fetch daily prices, build weekly, compute regime, and print results."""
    try:
        provider = get_market_data_provider()
        df_daily = provider.get_daily("SPY", lookback=400)
    except Exception as exc:
        print(f"Failed to fetch daily prices: {exc}", file=sys.stderr)
        return 1

    # Build weekly candles from daily
    df_weekly = build_weekly_from_daily(df_daily)

    if df_weekly.empty:
        print("Warning: Weekly data is empty", file=sys.stderr)

    # Compute regime
    try:
        result = compute_regime(df_daily, df_weekly, require_weekly_confirm=True)
    except Exception as exc:
        print(f"Failed to compute regime: {exc}", file=sys.stderr)
        return 1

    # Print results
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
