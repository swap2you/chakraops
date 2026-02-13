#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Diagnostic script to debug ORATS option chain data.

Usage:
    python scripts/debug_orats_chain.py AAPL
    python scripts/debug_orats_chain.py SPY --dte-min 21 --dte-max 45

This script:
- Calls ORATS /datav2/strikes/options directly
- Prints HTTP status, row count, sample contracts
- Shows count of contracts with valid liquidity
- No caching, no persistence, no evaluator logic
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests


ORATS_BASE = "https://api.orats.io/datav2"
ORATS_STRIKES_OPTIONS = "/strikes/options"
TIMEOUT_SEC = 15


def get_orats_token() -> str:
    """Get ORATS API token from environment or config."""
    # Try environment first
    token = os.environ.get("ORATS_API_TOKEN")
    if token:
        return token
    
    # Try config module
    try:
        from app.core.config.orats_secrets import ORATS_API_TOKEN
        return ORATS_API_TOKEN
    except ImportError:
        pass
    
    raise ValueError(
        "ORATS_API_TOKEN not found. Set environment variable or configure in app.core.config.orats_secrets"
    )


def fetch_strikes_options(
    ticker: str,
    dte_min: int = 7,
    dte_max: int = 60,
) -> dict:
    """
    Fetch option strikes from ORATS /datav2/strikes/options endpoint.
    
    Returns dict with:
        - status: HTTP status code
        - latency_ms: Request latency
        - rows: List of strike rows
        - error: Error message if any
    """
    token = get_orats_token()
    
    url = f"{ORATS_BASE}{ORATS_STRIKES_OPTIONS}"
    params = {
        "token": token,
        "ticker": ticker.upper(),
        "dte": f"{dte_min},{dte_max}",
    }
    
    t0 = time.perf_counter()
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_SEC)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        if r.status_code != 200:
            return {
                "status": r.status_code,
                "latency_ms": latency_ms,
                "rows": [],
                "error": f"HTTP {r.status_code}: {r.text[:200]}",
            }
        
        try:
            raw = r.json()
        except ValueError as e:
            return {
                "status": r.status_code,
                "latency_ms": latency_ms,
                "rows": [],
                "error": f"Invalid JSON: {e}",
            }
        
        # Extract rows
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict) and "data" in raw:
            rows = raw.get("data", [])
        else:
            rows = []
        
        return {
            "status": r.status_code,
            "latency_ms": latency_ms,
            "rows": rows,
            "error": None,
        }
        
    except requests.RequestException as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "status": 0,
            "latency_ms": latency_ms,
            "rows": [],
            "error": str(e),
        }


def analyze_liquidity(rows: list) -> dict:
    """
    Analyze liquidity from ORATS strike rows.
    
    Returns dict with:
        - total_rows: Total strike rows
        - calls_with_liquidity: Calls with valid bid/ask/OI
        - puts_with_liquidity: Puts with valid bid/ask/OI  
        - sample_calls: Sample call contracts
        - sample_puts: Sample put contracts
    """
    calls_valid = []
    puts_valid = []
    
    for row in rows:
        # Extract common fields
        strike = row.get("strike")
        expir = row.get("expirDate")
        dte = row.get("dte")
        delta = row.get("delta")
        
        # CALL contract
        call_bid = row.get("callBidPrice")
        call_ask = row.get("callAskPrice")
        call_vol = row.get("callVolume")
        call_oi = row.get("callOpenInterest")
        
        # Check call validity
        if call_bid is not None and call_ask is not None and call_oi is not None and call_oi > 0:
            calls_valid.append({
                "expir": expir,
                "strike": strike,
                "dte": dte,
                "type": "CALL",
                "bid": call_bid,
                "ask": call_ask,
                "mid": (call_bid + call_ask) / 2 if call_bid and call_ask else None,
                "volume": call_vol,
                "oi": call_oi,
                "delta": delta,
            })
        
        # PUT contract
        put_bid = row.get("putBidPrice")
        put_ask = row.get("putAskPrice")
        put_vol = row.get("putVolume")
        put_oi = row.get("putOpenInterest")
        
        # Check put validity
        if put_bid is not None and put_ask is not None and put_oi is not None and put_oi > 0:
            puts_valid.append({
                "expir": expir,
                "strike": strike,
                "dte": dte,
                "type": "PUT",
                "bid": put_bid,
                "ask": put_ask,
                "mid": (put_bid + put_ask) / 2 if put_bid and put_ask else None,
                "volume": put_vol,
                "oi": put_oi,
                "delta": -delta if delta else None,  # Put delta is negative
            })
    
    return {
        "total_rows": len(rows),
        "calls_with_liquidity": len(calls_valid),
        "puts_with_liquidity": len(puts_valid),
        "sample_calls": sorted(calls_valid, key=lambda x: x.get("oi") or 0, reverse=True)[:5],
        "sample_puts": sorted(puts_valid, key=lambda x: x.get("oi") or 0, reverse=True)[:5],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Debug ORATS option chain data for a symbol"
    )
    parser.add_argument("symbol", help="Stock symbol (e.g., AAPL, SPY)")
    parser.add_argument("--dte-min", type=int, default=7, help="Minimum DTE (default: 7)")
    parser.add_argument("--dte-max", type=int, default=60, help="Maximum DTE (default: 60)")
    
    args = parser.parse_args()
    symbol = args.symbol.upper()
    
    print(f"\n{'='*60}")
    print(f"ORATS Option Chain Diagnostic")
    print(f"Symbol: {symbol}")
    print(f"DTE Range: {args.dte_min} - {args.dte_max}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{'='*60}\n")
    
    # Fetch data
    print("[1] Fetching from ORATS /datav2/strikes/options...")
    result = fetch_strikes_options(symbol, args.dte_min, args.dte_max)
    
    print(f"\n[2] HTTP Response:")
    print(f"    Status: {result['status']}")
    print(f"    Latency: {result['latency_ms']}ms")
    print(f"    Row Count: {len(result['rows'])}")
    
    if result["error"]:
        print(f"    ERROR: {result['error']}")
        return 1
    
    if not result["rows"]:
        print("    WARNING: No data returned")
        return 1
    
    # Analyze liquidity
    print(f"\n[3] Liquidity Analysis:")
    analysis = analyze_liquidity(result["rows"])
    
    print(f"    Total Strike Rows: {analysis['total_rows']}")
    print(f"    Calls with Valid Liquidity: {analysis['calls_with_liquidity']}")
    print(f"    Puts with Valid Liquidity: {analysis['puts_with_liquidity']}")
    
    total_valid = analysis['calls_with_liquidity'] + analysis['puts_with_liquidity']
    print(f"    TOTAL Contracts with Liquidity: {total_valid}")
    
    # Sample contracts
    if analysis["sample_puts"]:
        print(f"\n[4] Top 5 PUT Contracts (by OI):")
        print(f"    {'Expiry':<12} {'Strike':>8} {'Bid':>8} {'Ask':>8} {'Vol':>8} {'OI':>8} {'Delta':>8}")
        print(f"    {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
        for c in analysis["sample_puts"]:
            delta_str = f"{c['delta']:.3f}" if c['delta'] else "N/A"
            print(f"    {c['expir']:<12} {c['strike']:>8.2f} {c['bid']:>8.2f} {c['ask']:>8.2f} {c['volume'] or 0:>8} {c['oi']:>8} {delta_str:>8}")
    
    if analysis["sample_calls"]:
        print(f"\n[5] Top 5 CALL Contracts (by OI):")
        print(f"    {'Expiry':<12} {'Strike':>8} {'Bid':>8} {'Ask':>8} {'Vol':>8} {'OI':>8} {'Delta':>8}")
        print(f"    {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
        for c in analysis["sample_calls"]:
            delta_str = f"{c['delta']:.3f}" if c['delta'] else "N/A"
            print(f"    {c['expir']:<12} {c['strike']:>8.2f} {c['bid']:>8.2f} {c['ask']:>8.2f} {c['volume'] or 0:>8} {c['oi']:>8} {delta_str:>8}")
    
    # Verdict
    print(f"\n[6] Liquidity Gate Verdict:")
    if analysis['puts_with_liquidity'] >= 3:
        print(f"    PASS: {analysis['puts_with_liquidity']} valid PUT contracts (need 3)")
    else:
        print(f"    FAIL: Only {analysis['puts_with_liquidity']} valid PUT contracts (need 3)")
    
    if total_valid >= 5:
        print(f"    PASS: {total_valid} total valid contracts (need 5)")
    else:
        print(f"    FAIL: Only {total_valid} total valid contracts (need 5)")
    
    # First strike row sample
    if result["rows"]:
        print(f"\n[7] Sample Raw Row (first):")
        sample = result["rows"][0]
        for key in ["expirDate", "strike", "stockPrice", "dte", 
                    "callBidPrice", "callAskPrice", "callVolume", "callOpenInterest",
                    "putBidPrice", "putAskPrice", "putVolume", "putOpenInterest",
                    "delta", "smvVol"]:
            val = sample.get(key, "MISSING")
            print(f"    {key}: {val}")
    
    print(f"\n{'='*60}")
    print(f"Diagnostic complete.")
    print(f"{'='*60}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
