#!/usr/bin/env python3
"""Real smoke test for ThetaData provider.

This script makes REAL API calls to ThetaData to verify:
1. Authentication works
2. Stock price fetching works
3. Daily candles fetching works
4. Options chain fetching works
5. Option mid price calculation works
6. DTE calculation works

IMPORTANT: This script requires:
- THETADATA_USERNAME environment variable
- THETADATA_PASSWORD environment variable
- thetadata package installed (pip install thetadata)

NO mocks. NO fake data. REAL API calls only.
"""

from __future__ import annotations

import os
import sys
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from app.core.market_data.thetadata_provider import ThetaDataProvider


def main() -> int:
    """Run real ThetaData smoke test."""
    print("=" * 60)
    print("ThetaData Real Smoke Test")
    print("=" * 60)
    print()
    
    # Check credentials
    username = os.getenv("THETADATA_USERNAME")
    password = os.getenv("THETADATA_PASSWORD")
    
    if not username or not password:
        print("ERROR: THETADATA_USERNAME and THETADATA_PASSWORD must be set", file=sys.stderr)
        return 1
    
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password)}")
    print()
    
    try:
        # Initialize provider
        print("Step 1: Initializing ThetaDataProvider...")
        provider = ThetaDataProvider()
        print("  ✓ Provider initialized")
        print()
    except Exception as e:
        print(f"  ✗ Failed to initialize provider: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    # Test symbol
    symbol = "AAPL"
    
    try:
        # Test 1: Get stock price
        print(f"Step 2: Fetching stock price for {symbol}...")
        price = provider.get_stock_price(symbol)
        print(f"  ✓ {symbol} price: ${price:.2f}")
        print()
    except Exception as e:
        print(f"  ✗ Failed to fetch stock price: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    try:
        # Test 2: Get daily candles
        print(f"Step 3: Fetching daily candles for {symbol} (last 5 days)...")
        df = provider.get_daily(symbol, lookback=5)
        print(f"  ✓ Fetched {len(df)} daily bars")
        print("  Last 5 days:")
        for _, row in df.tail(5).iterrows():
            date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])
            print(f"    {date_str}: O={row['open']:.2f} H={row['high']:.2f} L={row['low']:.2f} C={row['close']:.2f} V={row['volume']:,.0f}")
        print()
    except Exception as e:
        print(f"  ✗ Failed to fetch daily candles: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    try:
        # Test 3: Get options chain
        print(f"Step 4: Fetching options chain for {symbol}...")
        chain = provider.get_options_chain(symbol)
        print(f"  ✓ Options found: {len(chain)}")
        
        if not chain:
            print("  ⚠ No options found")
            return 0
        
        # Find nearest expiry
        expiries = sorted(set(c.expiry for c in chain))
        nearest_expiry = expiries[0] if expiries else None
        
        if nearest_expiry:
            dte = provider.get_dte(nearest_expiry)
            print(f"  Nearest expiry: {nearest_expiry} (DTE={dte})")
            
            # Filter chain for nearest expiry
            nearest_chain = [c for c in chain if c.expiry == nearest_expiry]
            print(f"  Contracts for {nearest_expiry}: {len(nearest_chain)}")
            
            # Find ATM call (closest to current price)
            calls = [c for c in nearest_chain if c.option_type == "CALL"]
            if calls:
                # Find ATM call (strike closest to current price)
                atm_call = min(calls, key=lambda c: abs(c.strike - price))
                print(f"  ATM call: Strike={atm_call.strike:.2f}, Mid=${atm_call.mid:.2f}")
                
                # Test get_option_mid_price
                try:
                    mid_price = provider.get_option_mid_price(
                        symbol, atm_call.strike, nearest_expiry, "CALL"
                    )
                    print(f"  ✓ get_option_mid_price() returned: ${mid_price:.2f}")
                except Exception as e:
                    print(f"  ✗ get_option_mid_price() failed: {e}", file=sys.stderr)
        print()
    except Exception as e:
        print(f"  ✗ Failed to fetch options chain: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    try:
        # Test 4: Get EMA
        print(f"Step 5: Calculating EMA50 for {symbol}...")
        ema50 = provider.get_ema(symbol, 50)
        print(f"  ✓ EMA50: ${ema50:.2f}")
        print()
    except Exception as e:
        print(f"  ✗ Failed to calculate EMA50: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 60)
    print("✓ All smoke tests passed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
