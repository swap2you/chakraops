#!/usr/bin/env python
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Diagnostic script to verify what ORATS /datav2/strikes/options returns
when called with underlying tickers.

This script:
1. Calls GET /datav2/strikes/options?tickers=AAPL,MSFT
2. Prints all keys in the response rows
3. Identifies which rows have optionSymbol (option rows) vs not (underlying rows)
4. Shows sample values for equity quote fields

Usage:
    python scripts/debug_orats_equity_quote.py [TICKER1,TICKER2,...]
"""

from __future__ import annotations

import json
import os
import sys

# Add chakraops to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

ORATS_BASE_URL = "https://api.orats.io/datav2"


def get_orats_token() -> str:
    """Get ORATS API token from config."""
    try:
        from app.core.config.orats_secrets import ORATS_API_TOKEN
        return ORATS_API_TOKEN
    except ImportError:
        # Fallback to env var
        token = os.environ.get("ORATS_API_TOKEN", "")
        if not token:
            raise ValueError("ORATS_API_TOKEN not found in config or environment")
        return token


def debug_strikes_options(tickers: list[str]) -> None:
    """Debug the /datav2/strikes/options response for underlying tickers."""
    
    print("=" * 80)
    print(f"DEBUG: ORATS /datav2/strikes/options with underlying tickers")
    print("=" * 80)
    
    token = get_orats_token()
    tickers_param = ",".join(tickers)
    
    url = f"{ORATS_BASE_URL}/strikes/options"
    params = {
        "token": token,
        "tickers": tickers_param,
    }
    
    print(f"\nRequest: GET {url}")
    print(f"Params: tickers={tickers_param}")
    print()
    
    r = requests.get(url, params=params, timeout=30)
    
    print(f"HTTP Status: {r.status_code}")
    
    if r.status_code != 200:
        print(f"ERROR: {r.text[:500]}")
        return
    
    raw = r.json()
    
    # Extract rows
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and "data" in raw:
        rows = raw.get("data", [])
    else:
        print(f"Unexpected response format: {type(raw)}")
        print(json.dumps(raw, indent=2)[:1000])
        return
    
    print(f"Total rows returned: {len(rows)}")
    print()
    
    # Separate underlying rows from option rows
    underlying_rows = [r for r in rows if not r.get("optionSymbol")]
    option_rows = [r for r in rows if r.get("optionSymbol")]
    
    print(f"Underlying rows (no optionSymbol): {len(underlying_rows)}")
    print(f"Option rows (has optionSymbol): {len(option_rows)}")
    print()
    
    # Analyze underlying rows
    if underlying_rows:
        print("=" * 60)
        print("UNDERLYING ROWS ANALYSIS")
        print("=" * 60)
        
        # Print all unique keys across underlying rows
        all_keys = set()
        for row in underlying_rows:
            all_keys.update(row.keys())
        
        print(f"\nAll keys in underlying rows ({len(all_keys)} keys):")
        for key in sorted(all_keys):
            print(f"  - {key}")
        
        print("\nSample underlying row values:")
        for row in underlying_rows[:3]:
            ticker = row.get("ticker", "UNKNOWN")
            print(f"\n  {ticker}:")
            
            # Show equity quote fields
            equity_fields = ["stockPrice", "bid", "ask", "bidSize", "askSize", 
                           "volume", "quoteDate", "updatedAt"]
            for field in equity_fields:
                value = row.get(field)
                print(f"    {field}: {value}")
            
            # Show a few other interesting fields
            other_fields = ["tradeDate", "dte", "expirDate", "strike"]
            for field in other_fields:
                if field in row:
                    print(f"    {field}: {row[field]}")
    else:
        print("\n*** NO UNDERLYING ROWS FOUND ***")
        print("This means /strikes/options with underlying tickers does NOT return underlying quotes.")
        print("The bid/ask/volume fields in the response are for OPTIONS, not the underlying stock.")
    
    # Analyze option rows (just a sample)
    if option_rows:
        print()
        print("=" * 60)
        print("OPTION ROWS ANALYSIS (sample)")
        print("=" * 60)
        
        # Print all unique keys
        all_keys = set()
        for row in option_rows[:10]:
            all_keys.update(row.keys())
        
        print(f"\nAll keys in option rows ({len(all_keys)} keys):")
        for key in sorted(all_keys):
            print(f"  - {key}")
        
        print("\nSample option row:")
        sample = option_rows[0]
        print(f"  optionSymbol: {sample.get('optionSymbol')}")
        print(f"  ticker: {sample.get('ticker')}")
        print(f"  stockPrice: {sample.get('stockPrice')}")
        print(f"  bidPrice: {sample.get('bidPrice')}")
        print(f"  askPrice: {sample.get('askPrice')}")
        print(f"  volume: {sample.get('volume')}")
        print(f"  openInterest: {sample.get('openInterest')}")
    
    print()
    print("=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    
    if underlying_rows:
        has_bid = any(r.get("bid") is not None for r in underlying_rows)
        has_ask = any(r.get("ask") is not None for r in underlying_rows)
        has_volume = any(r.get("volume") is not None for r in underlying_rows)
        has_stock_price = any(r.get("stockPrice") is not None for r in underlying_rows)
        
        print(f"  stockPrice available: {has_stock_price}")
        print(f"  bid available: {has_bid}")
        print(f"  ask available: {has_ask}")
        print(f"  volume available: {has_volume}")
    else:
        print("  No underlying rows - equity quotes NOT available from this endpoint with underlying tickers only.")
        
        if option_rows:
            has_stock_price = any(r.get("stockPrice") is not None for r in option_rows)
            print(f"\n  However, option rows DO contain stockPrice: {has_stock_price}")
            print("  We can extract stockPrice from option rows as fallback.")


def debug_ivrank(tickers: list[str]) -> None:
    """Debug the /datav2/ivrank response."""
    
    print()
    print("=" * 80)
    print(f"DEBUG: ORATS /datav2/ivrank")
    print("=" * 80)
    
    token = get_orats_token()
    tickers_param = ",".join(tickers)
    
    url = f"{ORATS_BASE_URL}/ivrank"
    params = {
        "token": token,
        "ticker": tickers_param,  # Note: singular 'ticker'
    }
    
    print(f"\nRequest: GET {url}")
    print(f"Params: ticker={tickers_param}")
    print()
    
    r = requests.get(url, params=params, timeout=30)
    
    print(f"HTTP Status: {r.status_code}")
    
    if r.status_code != 200:
        print(f"ERROR: {r.text[:500]}")
        return
    
    raw = r.json()
    
    # Extract rows
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and "data" in raw:
        rows = raw.get("data", [])
    else:
        rows = []
    
    print(f"Total rows returned: {len(rows)}")
    
    if rows:
        print("\nAll keys in rows:")
        all_keys = set()
        for row in rows:
            all_keys.update(row.keys())
        for key in sorted(all_keys):
            print(f"  - {key}")
        
        print("\nSample row values:")
        for row in rows[:3]:
            ticker = row.get("ticker", "UNKNOWN")
            print(f"\n  {ticker}:")
            print(f"    ivRank1m: {row.get('ivRank1m')}")
            print(f"    ivPct1m: {row.get('ivPct1m')}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        tickers = sys.argv[1].split(",")
    else:
        tickers = ["AAPL", "MSFT", "GOOGL"]
    
    print(f"Debugging ORATS with tickers: {tickers}")
    print()
    
    debug_strikes_options(tickers)
    debug_ivrank(tickers)
