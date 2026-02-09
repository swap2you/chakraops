#!/usr/bin/env python3
"""Smoke test for ThetaData v3 HTTP endpoints.

This script tests the basic ThetaData v3 HTTP API integration:
1. Fetch available symbols
2. Fetch available trade dates for AAPL
3. Fetch underlying price for AAPL (trade or daily fallback)

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
        # Test 3: Get underlying price (will try trade, then daily fallback)
        print(f"Step 4: Fetching underlying price for {test_symbol}...")
        print("  Attempting trade endpoint first...")
        
        # We'll manually test both endpoints to show which one was used
        price_source = None
        price = None
        
        # Try snapshot trade endpoint
        try:
            data = provider._make_request(
                "/stock/snapshot/trade",
                params={"symbol": test_symbol},
                format="json"
            )
            
            if isinstance(data, list) and len(data) > 0:
                result = data[0]
            elif isinstance(data, dict):
                result = data
            else:
                result = None
            
            if result:
                # Look for price field
                for field in ["price", "last", "trade_price", "close"]:
                    if field in result and result[field] is not None:
                        try:
                            price = float(result[field])
                            if price > 0:
                                price_source = "trade"
                                print(f"  [OK] Trade endpoint returned price: ${price:.2f}")
                                print(f"  Source: /stock/trade (latest trade)")
                                break
                        except (ValueError, TypeError):
                            continue
        except Exception as e:
            print(f"  [INFO] Trade endpoint failed: {e}")
            print("  Falling back to daily endpoint...")
        
        # Try EOD endpoint if trade didn't work
        if price_source is None:
            try:
                from datetime import date
                today = date.today()
                today_str = today.strftime("%Y%m%d")
                
                data = provider._make_request(
                    "/stock/history/eod",
                    params={
                        "symbol": test_symbol,
                        "start_date": today_str,
                        "end_date": today_str
                    },
                    format="json"
                )
                
                if isinstance(data, list) and len(data) > 0:
                    result = data[0]
                elif isinstance(data, dict):
                    result = data
                else:
                    result = None
                
                if result:
                    # Look for close price
                    for field in ["close", "price", "last"]:
                        if field in result and result[field] is not None:
                            try:
                                price = float(result[field])
                                if price > 0:
                                    price_source = "daily"
                                    print(f"  [OK] Daily endpoint returned price: ${price:.2f}")
                                    print(f"  Source: /stock/history/eod (latest close)")
                                    break
                            except (ValueError, TypeError):
                                continue
            except Exception as e:
                print(f"  [FAIL] EOD endpoint also failed: {e}", file=sys.stderr)
        
        # Now test the actual get_underlying_price method
        if price_source:
            print()
            print(f"  Testing get_underlying_price() method...")
            method_price = provider.get_underlying_price(test_symbol)
            print(f"  [OK] get_underlying_price() returned: ${method_price:.2f}")
            print(f"  [OK] Price source: {price_source}")
        else:
            print()
            print(f"  Testing get_underlying_price() method...")
            try:
                method_price = provider.get_underlying_price(test_symbol)
                print(f"  [OK] get_underlying_price() returned: ${method_price:.2f}")
            except ProviderDataError as e:
                print(f"  [FAIL] ProviderDataError: {e}", file=sys.stderr)
                return 1
        print()
    except ProviderDataError as e:
        print(f"  [FAIL] ProviderDataError: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"  [FAIL] Failed to fetch underlying price: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 60)
    print("[OK] All smoke tests passed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
