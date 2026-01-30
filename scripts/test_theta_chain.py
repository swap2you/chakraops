#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Diagnostic script to test which Theta API endpoints return data.

Tests multiple endpoints to determine which works for your subscription:
- /option/snapshot/ohlc (per-strike)
- /option/snapshot/quote (per-strike or wildcard)
- /option/snapshot/all_greeks (if available)

Usage:
    python scripts/test_theta_chain.py AAPL
    python scripts/test_theta_chain.py AAPL --dte-min 7 --dte-max 45 --strike-limit 5
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

import httpx

from app.core.settings import get_theta_base_url, get_theta_timeout


def _parse_date(exp: str) -> Optional[date]:
    """Parse expiration string to date."""
    try:
        clean = exp.replace("-", "")[:8]
        if len(clean) == 8 and clean.isdigit():
            return date(int(clean[:4]), int(clean[4:6]), int(clean[6:8]))
    except (ValueError, TypeError):
        pass
    return None


def _normalize_expiration(exp: str) -> str:
    """Normalize expiration to YYYYMMDD format."""
    return exp.replace("-", "").replace("/", "")[:8]


def test_list_expirations(symbol: str, base_url: str, timeout: float) -> List[str]:
    """Test /option/list/expirations endpoint."""
    print(f"\n[1] Testing /option/list/expirations for {symbol}...")
    
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                f"{base_url}/option/list/expirations",
                params={"symbol": symbol, "format": "json"},
            )
            print(f"    Status: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"    Error: HTTP {resp.status_code}")
                return []
            
            data = resp.json()
            
            # Parse response
            if isinstance(data, dict):
                data = data.get("response") or data.get("expirations") or []
            
            expirations = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        expirations.append(item)
                    elif isinstance(item, dict):
                        exp = item.get("expiration") or item.get("exp") or item.get("date")
                        if exp:
                            expirations.append(str(exp))
                    elif isinstance(item, int):
                        expirations.append(str(item))
            
            print(f"    Found {len(expirations)} expirations")
            if expirations[:5]:
                print(f"    First 5: {expirations[:5]}")
            
            return expirations
            
    except Exception as e:
        print(f"    Exception: {e}")
        return []


def test_list_strikes(symbol: str, expiration: str, base_url: str, timeout: float) -> List[float]:
    """Test /option/list/strikes endpoint."""
    exp_norm = _normalize_expiration(expiration)
    print(f"\n[2] Testing /option/list/strikes for {symbol} {expiration}...")
    
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                f"{base_url}/option/list/strikes",
                params={"symbol": symbol, "expiration": exp_norm, "format": "json"},
            )
            print(f"    Status: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"    Error: HTTP {resp.status_code}")
                return []
            
            data = resp.json()
            
            # Parse response
            if isinstance(data, dict):
                data = data.get("response") or data.get("strikes") or []
            
            strikes = []
            if isinstance(data, list):
                for item in data:
                    try:
                        if isinstance(item, (int, float)):
                            val = float(item)
                            if val > 10000:  # Likely in millis
                                val = val / 1000
                            strikes.append(val)
                        elif isinstance(item, dict):
                            strike_val = item.get("strike") or item.get("price")
                            if strike_val is not None:
                                val = float(strike_val)
                                if val > 10000:
                                    val = val / 1000
                                strikes.append(val)
                    except (TypeError, ValueError):
                        continue
            
            strikes = sorted(strikes)
            print(f"    Found {len(strikes)} strikes")
            if strikes[:5]:
                print(f"    First 5: {strikes[:5]}")
            
            return strikes
            
    except Exception as e:
        print(f"    Exception: {e}")
        return []


def test_snapshot_ohlc(
    symbol: str, expiration: str, strike: float, right: str,
    base_url: str, timeout: float
) -> Dict[str, Any]:
    """Test /option/snapshot/ohlc endpoint (per-strike)."""
    exp_norm = _normalize_expiration(expiration)
    strike_int = int(strike * 1000)
    
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                f"{base_url}/option/snapshot/ohlc",
                params={
                    "symbol": symbol,
                    "expiration": exp_norm,
                    "strike": strike_int,
                    "right": right.upper(),
                    "format": "json",
                },
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "response" in data:
                    rows = data["response"]
                    if isinstance(rows, list) and rows:
                        return {"status": "OK", "data": rows[0], "code": 200}
                elif isinstance(data, list) and data:
                    return {"status": "OK", "data": data[0], "code": 200}
            
            return {"status": "EMPTY", "code": resp.status_code}
            
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def test_snapshot_quote(
    symbol: str, expiration: str, strike: float, right: str,
    base_url: str, timeout: float
) -> Dict[str, Any]:
    """Test /option/snapshot/quote endpoint (per-strike)."""
    exp_norm = _normalize_expiration(expiration)
    strike_int = int(strike * 1000)
    
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                f"{base_url}/option/snapshot/quote",
                params={
                    "symbol": symbol,
                    "expiration": exp_norm,
                    "strike": strike_int,
                    "right": right.upper(),
                    "format": "json",
                },
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "response" in data:
                    rows = data["response"]
                    if isinstance(rows, list) and rows:
                        return {"status": "OK", "data": rows[0], "code": 200}
                elif isinstance(data, list) and data:
                    return {"status": "OK", "data": data[0], "code": 200}
            
            return {"status": "EMPTY", "code": resp.status_code}
            
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def test_snapshot_quote_bulk(
    symbol: str, expiration: str,
    base_url: str, timeout: float
) -> Dict[str, Any]:
    """Test /option/snapshot/quote endpoint (bulk - all strikes for an expiration)."""
    exp_norm = _normalize_expiration(expiration)
    
    print(f"\n[5] Testing /option/snapshot/quote BULK for {symbol} {expiration}...")
    
    try:
        with httpx.Client(timeout=timeout) as client:
            # Try without strike parameter to get all strikes
            resp = client.get(
                f"{base_url}/option/snapshot/quote",
                params={
                    "symbol": symbol,
                    "expiration": exp_norm,
                    "format": "json",
                },
            )
            print(f"    Status: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "response" in data:
                    rows = data["response"]
                    if isinstance(rows, list) and rows:
                        print(f"    Returned {len(rows)} contracts")
                        if rows[0]:
                            print(f"    Sample keys: {list(rows[0].keys())[:10]}")
                        return {"status": "OK", "count": len(rows), "code": 200, "sample": rows[0] if rows else None}
            
            return {"status": "EMPTY", "code": resp.status_code}
            
    except Exception as e:
        print(f"    Exception: {e}")
        return {"status": "ERROR", "error": str(e)}


def test_snapshot_ohlc_bulk(
    symbol: str, expiration: str,
    base_url: str, timeout: float
) -> Dict[str, Any]:
    """Test /option/snapshot/ohlc endpoint (bulk - all strikes for an expiration)."""
    exp_norm = _normalize_expiration(expiration)
    
    print(f"\n[6] Testing /option/snapshot/ohlc BULK for {symbol} {expiration}...")
    
    try:
        with httpx.Client(timeout=timeout) as client:
            # Try without strike parameter to get all strikes
            resp = client.get(
                f"{base_url}/option/snapshot/ohlc",
                params={
                    "symbol": symbol,
                    "expiration": exp_norm,
                    "format": "json",
                },
            )
            print(f"    Status: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "response" in data:
                    rows = data["response"]
                    if isinstance(rows, list) and rows:
                        print(f"    Returned {len(rows)} contracts")
                        if rows[0]:
                            print(f"    Sample keys: {list(rows[0].keys())[:10]}")
                        return {"status": "OK", "count": len(rows), "code": 200, "sample": rows[0] if rows else None}
            
            return {"status": "EMPTY", "code": resp.status_code}
            
    except Exception as e:
        print(f"    Exception: {e}")
        return {"status": "ERROR", "error": str(e)}


def run_diagnostics(
    symbol: str,
    dte_min: int = 7,
    dte_max: int = 45,
    strike_limit: int = 5,
    expiration_limit: int = 2,
) -> Dict[str, Any]:
    """Run full diagnostic suite for a symbol."""
    symbol = symbol.upper()
    base_url = get_theta_base_url().rstrip("/")
    timeout = get_theta_timeout()
    
    print("=" * 60)
    print(f"THETA API DIAGNOSTIC - {symbol}")
    print(f"Base URL: {base_url}")
    print(f"Timeout: {timeout}s")
    print(f"DTE Window: {dte_min}-{dte_max} days")
    print(f"Strike Limit: {strike_limit} per expiration")
    print("=" * 60)
    
    results = {
        "symbol": symbol,
        "list_expirations": False,
        "list_strikes": False,
        "snapshot_ohlc_per_strike": False,
        "snapshot_quote_per_strike": False,
        "snapshot_ohlc_bulk": False,
        "snapshot_quote_bulk": False,
        "recommended_endpoint": None,
    }
    
    # Test 1: List expirations
    expirations = test_list_expirations(symbol, base_url, timeout)
    results["list_expirations"] = bool(expirations)
    
    if not expirations:
        print("\n[FAILED] Cannot list expirations - no further tests possible")
        return results
    
    # Filter to DTE window
    today = date.today()
    valid_expirations = []
    for exp in expirations:
        exp_date = _parse_date(exp)
        if exp_date:
            dte = (exp_date - today).days
            if dte_min <= dte <= dte_max:
                valid_expirations.append(exp)
        if len(valid_expirations) >= expiration_limit:
            break
    
    if not valid_expirations:
        print(f"\n[WARNING] No expirations in DTE window [{dte_min}-{dte_max}]")
        # Use first available expiration for testing
        if expirations:
            valid_expirations = expirations[:expiration_limit]
            print(f"    Using first {len(valid_expirations)} expirations for testing")
    
    test_expiration = valid_expirations[0]
    
    # Test 2: List strikes
    strikes = test_list_strikes(symbol, test_expiration, base_url, timeout)
    results["list_strikes"] = bool(strikes)
    
    if not strikes:
        print("\n[FAILED] Cannot list strikes - testing bulk endpoints only")
    else:
        # Take strikes near the middle (closer to ATM)
        mid_idx = len(strikes) // 2
        half_limit = strike_limit // 2
        test_strikes = strikes[max(0, mid_idx - half_limit):mid_idx + half_limit + 1][:strike_limit]
        
        # Test 3: snapshot_ohlc per-strike
        print(f"\n[3] Testing /option/snapshot/ohlc PER-STRIKE for {test_expiration}...")
        ohlc_ok = False
        for strike in test_strikes:
            for right in ("C", "P"):
                result = test_snapshot_ohlc(symbol, test_expiration, strike, right, base_url, timeout)
                if result["status"] == "OK":
                    print(f"    ✓ snapshot_ohlc OK for {right} ${strike:.2f}")
                    ohlc_ok = True
                    results["snapshot_ohlc_per_strike"] = True
                    break
            if ohlc_ok:
                break
        if not ohlc_ok:
            print(f"    ✗ snapshot_ohlc returned no data for {len(test_strikes)} strikes")
        
        # Test 4: snapshot_quote per-strike
        print(f"\n[4] Testing /option/snapshot/quote PER-STRIKE for {test_expiration}...")
        quote_ok = False
        for strike in test_strikes:
            for right in ("C", "P"):
                result = test_snapshot_quote(symbol, test_expiration, strike, right, base_url, timeout)
                if result["status"] == "OK":
                    print(f"    ✓ snapshot_quote OK for {right} ${strike:.2f}")
                    quote_ok = True
                    results["snapshot_quote_per_strike"] = True
                    break
            if quote_ok:
                break
        if not quote_ok:
            print(f"    ✗ snapshot_quote returned no data for {len(test_strikes)} strikes")
    
    # Test 5: snapshot_quote bulk (no strike param)
    bulk_quote_result = test_snapshot_quote_bulk(symbol, test_expiration, base_url, timeout)
    results["snapshot_quote_bulk"] = bulk_quote_result["status"] == "OK"
    
    # Test 6: snapshot_ohlc bulk (no strike param)
    bulk_ohlc_result = test_snapshot_ohlc_bulk(symbol, test_expiration, base_url, timeout)
    results["snapshot_ohlc_bulk"] = bulk_ohlc_result["status"] == "OK"
    
    # Determine recommended endpoint
    print("\n" + "=" * 60)
    print("DIAGNOSTIC RESULTS")
    print("=" * 60)
    
    for key, value in results.items():
        if key != "recommended_endpoint" and key != "symbol":
            status = "✓" if value else "✗"
            print(f"  {status} {key}: {value}")
    
    # Recommendation logic
    if results["snapshot_ohlc_bulk"]:
        results["recommended_endpoint"] = "ohlc_bulk"
        print("\n[RECOMMENDATION] Use snapshot_ohlc BULK (no strike param)")
        print("  This fetches all contracts for an expiration in one call.")
    elif results["snapshot_quote_bulk"]:
        results["recommended_endpoint"] = "quote_bulk"
        print("\n[RECOMMENDATION] Use snapshot_quote BULK (no strike param)")
        print("  This fetches all contracts for an expiration in one call.")
    elif results["snapshot_ohlc_per_strike"]:
        results["recommended_endpoint"] = "ohlc_per_strike"
        print("\n[RECOMMENDATION] Use snapshot_ohlc PER-STRIKE")
        print("  Requires calling API for each strike individually.")
    elif results["snapshot_quote_per_strike"]:
        results["recommended_endpoint"] = "quote_per_strike"
        print("\n[RECOMMENDATION] Use snapshot_quote PER-STRIKE")
        print("  Requires calling API for each strike individually.")
    else:
        print("\n[WARNING] No working endpoint found!")
        print("  Check your Theta subscription level and API key.")
    
    print("=" * 60)
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Test Theta API endpoints for a single symbol"
    )
    parser.add_argument("symbol", help="Ticker symbol to test (e.g., AAPL)")
    parser.add_argument("--dte-min", type=int, default=7, help="Minimum DTE (default: 7)")
    parser.add_argument("--dte-max", type=int, default=45, help="Maximum DTE (default: 45)")
    parser.add_argument("--strike-limit", type=int, default=5, help="Max strikes to test (default: 5)")
    parser.add_argument("--expiration-limit", type=int, default=2, help="Max expirations to test (default: 2)")
    
    args = parser.parse_args()
    
    results = run_diagnostics(
        args.symbol,
        dte_min=args.dte_min,
        dte_max=args.dte_max,
        strike_limit=args.strike_limit,
        expiration_limit=args.expiration_limit,
    )
    
    # Exit with code based on whether any endpoint works
    if results.get("recommended_endpoint"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
