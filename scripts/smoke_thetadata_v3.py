#!/usr/bin/env python3
"""Smoke test for ThetaData v3 HTTP endpoints.

This script tests the basic ThetaData v3 HTTP API integration:
1. Fetch available symbols
2. Fetch available trade dates for AAPL
3. Fetch last price for AAPL

IMPORTANT: This script requires ThetaData Terminal v3 to be running locally
on port 25503 (http://127.0.0.1:25503).

NO mocks. NO fake data. REAL API calls only.
"""

from __future__ import annotations

import sys

from app.core.market_data.thetadata_provider import ThetaDataProvider, ProviderDataError


def main() -> int:
    """Run ThetaData v3 smoke test."""
    print("=" * 60)
    print("ThetaData v3 HTTP API Smoke Test")
    print("=" * 60)
    print()
    print("IMPORTANT: ThetaData Terminal v3 must be running on port 25503")
    print()
    
    try:
        # Initialize provider
        print("Step 1: Initializing ThetaDataProvider...")
        provider = ThetaDataProvider()
        print("  [OK] Provider initialized successfully")
        print(f"  Base URL: {provider.base_url}")
        print()
    except ValueError as e:
        print(f"  [FAIL] Failed to initialize provider: {e}", file=sys.stderr)
        print("  Make sure ThetaData Terminal v3 is running!", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"  [FAIL] Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    # Test symbol
    test_symbol = "AAPL"
    
    try:
        # Test 1: Get available symbols
        print("Step 2: Fetching available symbols...")
        symbols = provider.get_available_symbols()
        print(f"  [OK] Fetched {len(symbols)} symbols")
        print(f"  First 10 symbols: {', '.join(symbols[:10])}")
        
        # Verify test symbol is in list
        if test_symbol in symbols:
            print(f"  [OK] Test symbol '{test_symbol}' found in symbol list")
        else:
            print(f"  [WARN] Test symbol '{test_symbol}' not found in symbol list")
        print()
    except ProviderDataError as e:
        print(f"  [FAIL] ProviderDataError: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"  [FAIL] Failed to fetch symbols: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    try:
        # Test 2: Get available dates
        print(f"Step 3: Fetching available trade dates for {test_symbol}...")
        dates = provider.get_available_dates(test_symbol, request_type="trade")
        print(f"  [OK] Fetched {len(dates)} available dates")
        
        if dates:
            print(f"  First 5 dates: {', '.join(dates[:5])}")
            print(f"  Last 5 dates: {', '.join(dates[-5:])}")
        print()
    except ProviderDataError as e:
        print(f"  [FAIL] ProviderDataError: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"  [FAIL] Failed to fetch dates: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    try:
        # Test 3: Get last price
        print(f"Step 4: Fetching last price for {test_symbol}...")
        price, timestamp = provider.get_stock_last_price(test_symbol)
        print(f"  [OK] Last price: ${price:.2f}")
        print(f"  [OK] Timestamp: {timestamp}")
        print()
    except ProviderDataError as e:
        # Check if it's a subscription issue
        if "403" in str(e) or "subscription" in str(e).lower():
            print(f"  [SKIP] Price endpoint requires subscription: {e}")
            print("  Note: /stock/snapshot/quote requires 'value' subscription or higher")
            print("  This is expected with a FREE subscription")
            print()
        else:
            print(f"  [FAIL] ProviderDataError: {e}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"  [FAIL] Failed to fetch last price: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 60)
    print("[OK] All smoke tests passed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
