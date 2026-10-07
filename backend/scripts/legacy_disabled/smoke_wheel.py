#!/usr/bin/env python3
"""Simple smoke test for CSP candidate finder."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from app.core.regime import build_weekly_from_daily, compute_regime
from app.core.wheel import find_csp_candidates
from app.core.market_data.factory import get_market_data_provider


def load_universe_seed() -> list[str]:
    """Load symbol universe from data/universe_seed.txt."""
    repo_root = Path(__file__).parent.parent
    seed_file = repo_root / "app" / "data" / "universe_seed.txt"
    
    if not seed_file.exists():
        raise FileNotFoundError(f"Universe seed file not found: {seed_file}")
    
    symbols = []
    with open(seed_file, "r") as f:
        for line in f:
            symbol = line.strip()
            if symbol and not symbol.startswith("#"):
                symbols.append(symbol.upper())
    
    return symbols


def main() -> int:
    """Load universe, fetch OHLC, compute regime, and find CSP candidates."""
    try:
        # Load universe
        symbols = load_universe_seed()
        print(f"Loaded {len(symbols)} symbols from universe_seed.txt", file=sys.stderr)
        
        # Fetch daily prices for SPY to compute regime
        provider = get_market_data_provider()
        df_spy_daily = provider.get_daily("SPY", lookback=400)
        
        # Build weekly and compute regime
        df_spy_weekly = build_weekly_from_daily(df_spy_daily)
        regime_result = compute_regime(df_spy_daily, df_spy_weekly, require_weekly_confirm=True)
        regime = regime_result["regime"]
        
        print(f"Regime: {regime} (confidence: {regime_result['confidence']}%)", file=sys.stderr)
        
        if regime != "RISK_ON":
            print("Not RISK_ON regime, no CSP candidates", file=sys.stderr)
            return 0
        
        # Fetch OHLC for all symbols in universe
        symbol_to_df = {}
        for symbol in symbols:
            try:
                df = provider.get_daily(symbol, lookback=300)
                symbol_to_df[symbol] = df
                print(f"Fetched {symbol}: {len(df)} bars", file=sys.stderr)
            except Exception as exc:
                print(f"Failed to fetch {symbol}: {exc}", file=sys.stderr)
                continue
        
        # Find CSP candidates
        candidates = find_csp_candidates(symbol_to_df, regime)
        
        # Print top candidates
        print(f"\nFound {len(candidates)} CSP candidates:", file=sys.stderr)
        print(json.dumps(candidates, indent=2))
        
        return 0
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
