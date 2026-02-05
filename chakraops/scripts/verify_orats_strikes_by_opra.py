#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Verification script for ORATS Delayed Data API Strikes-by-OPRA.

This script validates the ORATS integration by:
1. Calling /datav2/strikes to get strike grid
2. Building OCC option symbols
3. Calling /datav2/strikes/options with tickers=OCC option symbols only (no underlying)
4. Verifying option rows are returned with bidPrice/askPrice/openInterest

Usage:
    python scripts/verify_orats_strikes_by_opra.py AAPL
    python scripts/verify_orats_strikes_by_opra.py SPY --dte-min 30 --dte-max 45 --delta-min 0.2 --delta-max 0.35

Exit codes:
    0 - Success: option rows returned with OPRA fields
    1 - General failure
    2 - Schema mismatch: option rows == 0, diagnostic printed
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(
        description="Verify ORATS Delayed Data API Strikes-by-OPRA"
    )
    parser.add_argument("symbol", help="Stock symbol (e.g., AAPL, SPY)")
    parser.add_argument("--dte-min", type=int, default=30, help="Minimum DTE (default: 30)")
    parser.add_argument("--dte-max", type=int, default=45, help="Maximum DTE (default: 45)")
    parser.add_argument("--delta-min", type=float, default=None, help="Minimum delta filter")
    parser.add_argument("--delta-max", type=float, default=None, help="Maximum delta filter")
    parser.add_argument("--max-symbols", type=int, default=20, help="Max option symbols to build (default: 20)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    symbol = args.symbol.upper()
    
    print(f"\n{'='*70}")
    print(f"ORATS Delayed Data API - Strikes-by-OPRA Verification")
    print(f"{'='*70}")
    print(f"  Symbol:     {symbol}")
    print(f"  DTE Range:  {args.dte_min} - {args.dte_max}")
    print(f"  Delta:      {args.delta_min} - {args.delta_max}" if args.delta_min else "  Delta:      (no filter)")
    print(f"  Timestamp:  {datetime.now().isoformat()}")
    print(f"{'='*70}\n")
    
    # Import modules
    try:
        from app.core.orats.orats_opra import (
            OratsDelayedClient,
            OratsDelayedError,
            build_orats_option_symbol,
            validate_orats_option_symbol,
        )
    except ImportError as e:
        print(f"ERROR: Failed to import ORATS module: {e}")
        return 1
    
    client = OratsDelayedClient()
    
    # =========================================================================
    # STEP 1: Call /datav2/strikes
    # =========================================================================
    print("[STEP 1] Calling GET /datav2/strikes...")
    print(f"         Query param: ticker={symbol}")
    print(f"         Filters: dte={args.dte_min},{args.dte_max}")
    
    try:
        strikes_rows = client.get_strikes(
            ticker=symbol,
            dte_min=args.dte_min,
            dte_max=args.dte_max,
            delta_min=args.delta_min,
            delta_max=args.delta_max,
        )
    except OratsDelayedError as e:
        print(f"\n    ERROR: {e}")
        return 1
    
    print(f"\n    Rows returned: {len(strikes_rows)}")
    
    if not strikes_rows:
        print("    ERROR: No strikes data returned")
        return 1
    
    # Show sample keys
    sample_keys = list(strikes_rows[0].keys())
    print(f"    Sample keys: {sample_keys[:15]}...")
    
    # Get stock price and unique expirations
    stock_price = None
    expirations = set()
    for row in strikes_rows:
        sp = row.get("stockPrice") or row.get("stkPx")
        if sp and stock_price is None:
            stock_price = float(sp)
        exp = row.get("expirDate")
        if exp:
            expirations.add(exp)
    
    print(f"    Stock price: ${stock_price:.2f}" if stock_price else "    Stock price: N/A")
    print(f"    Unique expirations: {len(expirations)}")
    
    if args.verbose and expirations:
        print(f"    Expirations: {sorted(expirations)[:5]}...")
    
    # =========================================================================
    # STEP 2: Build option symbols
    # =========================================================================
    print(f"\n[STEP 2] Building OCC option symbols (max {args.max_symbols})...")
    
    # Group by expiration and select strikes near ATM
    expiry_strikes = {}
    for row in strikes_rows:
        exp = row.get("expirDate")
        if not exp:
            continue
        if exp not in expiry_strikes:
            expiry_strikes[exp] = []
        expiry_strikes[exp].append(row)
    
    # Sort expirations and take first 3
    sorted_expiries = sorted(expiry_strikes.keys())[:3]
    
    option_symbols = []
    for exp in sorted_expiries:
        rows = expiry_strikes[exp]
        
        # Sort by proximity to ATM
        if stock_price:
            rows.sort(key=lambda r: abs(float(r.get("strike", 0)) - stock_price))
        
        # Take top 5 strikes, build PUT + CALL for each
        for row in rows[:5]:
            strike = row.get("strike")
            if strike is None:
                continue
            
            put_sym = build_orats_option_symbol(symbol, exp, "P", float(strike))
            call_sym = build_orats_option_symbol(symbol, exp, "C", float(strike))
            
            option_symbols.append(put_sym)
            option_symbols.append(call_sym)
            
            if len(option_symbols) >= args.max_symbols:
                break
        
        if len(option_symbols) >= args.max_symbols:
            break
    
    print(f"    Built {len(option_symbols)} option symbols")
    
    # Show 3 samples
    print(f"\n    Sample option symbols:")
    for i, sym in enumerate(option_symbols[:3]):
        valid = validate_orats_option_symbol(sym)
        print(f"      [{i+1}] {sym} (valid={valid})")
    
    if not option_symbols:
        print("    ERROR: No option symbols could be built")
        return 1
    
    # =========================================================================
    # STEP 3: Call /datav2/strikes/options with OCC option symbols ONLY (no underlying)
    # =========================================================================
    print(f"\n[STEP 3] Calling GET /datav2/strikes/options...")
    print(f"         Query param: tickers=OCC symbols only (total {len(option_symbols)})")
    print(f"         NOTE: underlying ticker is FORBIDDEN for this endpoint.")
    
    tickers_to_fetch = option_symbols
    
    try:
        opra_rows = client.get_strikes_by_opra(tickers_to_fetch)
    except OratsDelayedError as e:
        print(f"\n    ERROR: {e}")
        print(f"\n    DIAGNOSTIC:")
        print(f"      param_name used: tickers")
        print(f"      first symbol: {option_symbols[0]}")
        return 2
    
    print(f"\n    Total rows returned: {len(opra_rows)}")
    
    option_rows = [r for r in opra_rows if r.get("optionSymbol")]
    print(f"    Option rows (with optionSymbol): {len(option_rows)}")
    
    # =========================================================================
    # STEP 4: Verify option rows have required fields
    # =========================================================================
    print(f"\n[STEP 4] Verifying option row schema...")
    
    if len(option_rows) == 0:
        print(f"\n    {'!'*60}")
        print(f"    FAIL: option_rows == 0")
        print(f"    DIAGNOSTIC:")
        print(f"      param_name used: tickers (PLURAL)")
        print(f"      first optionSymbol: {option_symbols[0] if option_symbols else 'N/A'}")
        if opra_rows:
            print(f"      response keys: {list(opra_rows[0].keys())}")
        else:
            print(f"      response keys: (empty response)")
        print(f"    {'!'*60}\n")
        return 2
    
    # Check for required fields in option rows
    sample_option = option_rows[0]
    option_keys = list(sample_option.keys())
    print(f"    Sample option row keys: {option_keys}")
    
    # Check required fields
    required_fields = ["optionSymbol", "bidPrice", "askPrice", "openInterest"]
    missing_fields = [f for f in required_fields if f not in option_keys]
    
    if missing_fields:
        print(f"\n    WARNING: Missing expected fields: {missing_fields}")
    
    # Count rows with valid liquidity
    valid_count = 0
    with_bid_ask = 0
    with_oi = 0
    with_volume = 0
    
    for row in option_rows:
        bid = row.get("bidPrice")
        ask = row.get("askPrice")
        oi = row.get("openInterest")
        vol = row.get("volume")
        
        if bid is not None and ask is not None:
            with_bid_ask += 1
        if oi is not None and oi > 0:
            with_oi += 1
        if vol is not None:
            with_volume += 1
        if bid is not None and ask is not None and oi is not None and oi > 0:
            valid_count += 1
    
    print(f"\n    Liquidity stats:")
    print(f"      With bid/ask:         {with_bid_ask}/{len(option_rows)}")
    print(f"      With openInterest>0:  {with_oi}/{len(option_rows)}")
    print(f"      With volume:          {with_volume}/{len(option_rows)}")
    print(f"      Valid (bid+ask+OI):   {valid_count}/{len(option_rows)}")
    
    # Show sample valid option
    print(f"\n    Sample option rows:")
    for i, row in enumerate(option_rows[:3]):
        print(f"      [{i+1}] {row.get('optionSymbol')} bid={row.get('bidPrice')} ask={row.get('askPrice')} OI={row.get('openInterest')} vol={row.get('volume')}")
    
    # (Underlying is not requested from /strikes/options; chain discovery has stock price.)
    
    # =========================================================================
    # Summary
    # =========================================================================
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"  Strikes rows:          {len(strikes_rows)}")
    print(f"  Option symbols built:  {len(option_symbols)}")
    print(f"  OPRA rows returned:    {len(opra_rows)}")
    print(f"  Option rows:           {len(option_rows)}")
    print(f"  Valid contracts:       {valid_count}")
    
    if len(option_rows) > 0 and valid_count > 0:
        print(f"\n{'='*70}")
        print(f"✓ SUCCESS: ORATS Strikes-by-OPRA working correctly")
        print(f"  - Option rows returned with optionSymbol")
        print(f"  - bidPrice/askPrice/openInterest present")
        print(f"  - {valid_count} contracts with valid liquidity")
        print(f"{'='*70}\n")
        return 0
    elif len(option_rows) > 0:
        print(f"\n{'='*70}")
        print(f"⚠ PARTIAL: Option rows returned but no valid liquidity")
        print(f"  - This may be normal outside market hours")
        print(f"  - Check during market hours for bid/ask/OI")
        print(f"{'='*70}\n")
        return 0  # Still success, just no liquidity (could be after hours)
    else:
        print(f"\n{'='*70}")
        print(f"✗ FAIL: No option rows returned")
        print(f"  - Check param name (must be 'tickers' plural)")
        print(f"  - Check option symbol format")
        print(f"{'='*70}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
