#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Diagnostic script to test Theta API endpoints and validate strategy criteria.

Tests bulk endpoints and filters contracts based on strategy criteria:
- DTE window (7-45 days default)
- Delta range (for CSP: -0.30 to -0.10)
- Credit thresholds
- Bid/ask spread limits

Usage:
    # Basic diagnostic
    python scripts/test_theta_chain.py AAPL

    # Full strategy validation with filters
    python scripts/test_theta_chain.py AAPL --validate-strategy

    # Custom criteria
    python scripts/test_theta_chain.py AAPL --validate-strategy --min-delta -0.30 --max-delta -0.10 --min-credit 0.50
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

from app.core.settings import get_theta_base_url, get_theta_timeout, get_theta_endpoint


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
                    print(f"    [OK] snapshot_ohlc OK for {right} ${strike:.2f}")
                    ohlc_ok = True
                    results["snapshot_ohlc_per_strike"] = True
                    break
            if ohlc_ok:
                break
        if not ohlc_ok:
            print(f"    [X] snapshot_ohlc returned no data for {len(test_strikes)} strikes")
        
        # Test 4: snapshot_quote per-strike
        print(f"\n[4] Testing /option/snapshot/quote PER-STRIKE for {test_expiration}...")
        quote_ok = False
        for strike in test_strikes:
            for right in ("C", "P"):
                result = test_snapshot_quote(symbol, test_expiration, strike, right, base_url, timeout)
                if result["status"] == "OK":
                    print(f"    [OK] snapshot_quote OK for {right} ${strike:.2f}")
                    quote_ok = True
                    results["snapshot_quote_per_strike"] = True
                    break
            if quote_ok:
                break
        if not quote_ok:
            print(f"    [X] snapshot_quote returned no data for {len(test_strikes)} strikes")
    
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
            status = "[OK]" if value else "[X]"
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


def validate_strategy_criteria(
    symbol: str,
    dte_min: int = 7,
    dte_max: int = 45,
    min_delta: float = -0.30,
    max_delta: float = -0.10,
    min_credit: float = 0.30,
    max_spread_pct: float = 25.0,
    min_bid: float = 0.10,
) -> Dict[str, Any]:
    """Fetch chain via bulk endpoint and filter by strategy criteria.
    
    This validates that live data meets the strategy requirements for CSP candidates.
    
    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g., "AAPL")
    dte_min, dte_max : int
        DTE window for expirations
    min_delta, max_delta : float
        Delta range (for CSP, typically -0.30 to -0.10)
    min_credit : float
        Minimum premium/credit required
    max_spread_pct : float
        Maximum bid-ask spread as percentage
    min_bid : float
        Minimum bid price
    
    Returns
    -------
    dict
        Results including total contracts, filtered candidates, and examples
    """
    from app.data.theta_v3_pipeline import fetch_chain
    
    print("\n" + "=" * 60)
    print(f"STRATEGY CRITERIA VALIDATION - {symbol}")
    print("=" * 60)
    print(f"DTE Window: {dte_min}-{dte_max} days")
    print(f"Delta Range: {min_delta} to {max_delta}")
    print(f"Min Credit: ${min_credit:.2f}")
    print(f"Max Spread: {max_spread_pct}%")
    print(f"Min Bid: ${min_bid:.2f}")
    print("-" * 60)
    
    # Fetch chain using bulk endpoint
    endpoint = get_theta_endpoint()
    print(f"\nFetching chain via {endpoint}...")
    
    contracts = fetch_chain(symbol, dte_min=dte_min, dte_max=dte_max, endpoint=endpoint)
    
    if not contracts:
        print(f"[ERROR] No contracts returned for {symbol}")
        return {"symbol": symbol, "total_contracts": 0, "candidates": 0, "error": "No contracts"}
    
    # Split by type
    puts = [c for c in contracts if c.get("right") == "P"]
    calls = [c for c in contracts if c.get("right") == "C"]
    
    print(f"\nTotal contracts: {len(contracts)}")
    print(f"  PUTs: {len(puts)}")
    print(f"  CALLs: {len(calls)}")
    
    # Filter PUTs by strategy criteria (CSP)
    csp_candidates = []
    rejection_reasons = {
        "no_bid": 0,
        "bid_too_low": 0,
        "spread_too_wide": 0,
        "delta_out_of_range": 0,
        "credit_too_low": 0,
        "no_delta": 0,
    }
    
    for c in puts:
        bid = c.get("bid")
        ask = c.get("ask")
        delta = c.get("delta")
        
        # Check bid
        if bid is None or bid <= 0:
            rejection_reasons["no_bid"] += 1
            continue
        
        if bid < min_bid:
            rejection_reasons["bid_too_low"] += 1
            continue
        
        # Check spread
        if ask and ask > 0 and bid > 0:
            spread_pct = ((ask - bid) / bid) * 100
            if spread_pct > max_spread_pct:
                rejection_reasons["spread_too_wide"] += 1
                continue
        
        # Check delta (if available)
        if delta is not None:
            # For PUTs, delta is negative
            if not (min_delta <= delta <= max_delta):
                rejection_reasons["delta_out_of_range"] += 1
                continue
        else:
            rejection_reasons["no_delta"] += 1
            # Still include if other criteria pass (delta may not be in quote_bulk)
        
        # Check credit (bid is the credit received for selling)
        if bid < min_credit:
            rejection_reasons["credit_too_low"] += 1
            continue
        
        csp_candidates.append(c)
    
    print(f"\n[CSP CANDIDATE FILTERING]")
    print(f"  Total PUTs evaluated: {len(puts)}")
    print(f"  CSP Candidates: {len(csp_candidates)}")
    print(f"\n  Rejections:")
    for reason, count in rejection_reasons.items():
        if count > 0:
            print(f"    - {reason}: {count}")
    
    # Show sample candidates
    if csp_candidates:
        print(f"\n[SAMPLE CSP CANDIDATES]")
        for c in csp_candidates[:5]:
            strike = c.get("strike", 0)
            exp = c.get("expiration", "")
            bid = c.get("bid", 0)
            ask = c.get("ask", 0)
            delta = c.get("delta")
            dte = c.get("dte", 0)
            delta_str = f"{delta:.3f}" if delta is not None else "N/A"
            print(f"    {symbol} PUT ${strike:.0f} exp={exp} bid=${bid:.2f} ask=${ask:.2f} delta={delta_str} DTE={dte}")
    else:
        print(f"\n[WARNING] No CSP candidates found!")
        print("  Consider:")
        print("    - Lowering min_credit (current: ${:.2f})".format(min_credit))
        print("    - Widening delta range (current: {} to {})".format(min_delta, max_delta))
        print("    - Increasing max_spread_pct (current: {}%)".format(max_spread_pct))
        if rejection_reasons["no_delta"] > 0:
            print("    - Note: quote_bulk doesn't include delta; use ohlc_bulk or lower requirements")
    
    print("\n" + "=" * 60)
    
    return {
        "symbol": symbol,
        "total_contracts": len(contracts),
        "total_puts": len(puts),
        "total_calls": len(calls),
        "csp_candidates": len(csp_candidates),
        "rejections": rejection_reasons,
        "sample_candidates": csp_candidates[:5] if csp_candidates else [],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Test Theta API endpoints and validate strategy criteria"
    )
    parser.add_argument("symbol", help="Ticker symbol to test (e.g., AAPL)")
    parser.add_argument("--dte-min", type=int, default=7, help="Minimum DTE (default: 7)")
    parser.add_argument("--dte-max", type=int, default=45, help="Maximum DTE (default: 45)")
    parser.add_argument("--strike-limit", type=int, default=5, help="Max strikes to test per-strike mode (default: 5)")
    parser.add_argument("--expiration-limit", type=int, default=2, help="Max expirations for diagnostic (default: 2)")
    
    # Strategy validation options
    parser.add_argument("--validate-strategy", "-v", action="store_true",
                       help="Run strategy criteria validation after diagnostics")
    parser.add_argument("--min-delta", type=float, default=-0.30,
                       help="Min delta for CSP candidates (default: -0.30)")
    parser.add_argument("--max-delta", type=float, default=-0.10,
                       help="Max delta for CSP candidates (default: -0.10)")
    parser.add_argument("--min-credit", type=float, default=0.30,
                       help="Min credit/premium required (default: $0.30)")
    parser.add_argument("--max-spread-pct", type=float, default=25.0,
                       help="Max bid-ask spread percentage (default: 25%%)")
    parser.add_argument("--min-bid", type=float, default=0.10,
                       help="Minimum bid price (default: $0.10)")
    
    args = parser.parse_args()
    
    # Run endpoint diagnostics
    results = run_diagnostics(
        args.symbol,
        dte_min=args.dte_min,
        dte_max=args.dte_max,
        strike_limit=args.strike_limit,
        expiration_limit=args.expiration_limit,
    )
    
    # Run strategy validation if requested
    if args.validate_strategy:
        strategy_results = validate_strategy_criteria(
            args.symbol,
            dte_min=args.dte_min,
            dte_max=args.dte_max,
            min_delta=args.min_delta,
            max_delta=args.max_delta,
            min_credit=args.min_credit,
            max_spread_pct=args.max_spread_pct,
            min_bid=args.min_bid,
        )
        
        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Endpoint: {results.get('recommended_endpoint', 'unknown')}")
        print(f"  Total Contracts: {strategy_results.get('total_contracts', 0)}")
        print(f"  CSP Candidates: {strategy_results.get('csp_candidates', 0)}")
        
        if strategy_results.get("csp_candidates", 0) > 0:
            print("\n  [SUCCESS] Strategy validation PASSED")
            print("  Live data meets strategy criteria.")
        else:
            print("\n  [WARNING] Strategy validation found 0 candidates")
            print("  Adjust criteria or check data quality.")
    
    # Exit with code based on whether any endpoint works
    if results.get("recommended_endpoint"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
