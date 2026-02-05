#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Verification script for ORATS strikes/options endpoint.

This script validates the ORATS option chain pipeline with real API calls:
  STEP 1: GET /datav2/strikes → base chain discovery
  STEP 2: GET /datav2/strikes/options?ticker=OPRA1,... → liquidity enrichment

Usage:
    python scripts/verify_orats_strikes_options.py AAPL
    python scripts/verify_orats_strikes_options.py AAPL --mode delayed --dte-min 30 --dte-max 45
    python scripts/verify_orats_strikes_options.py SPY --verbose

Exit codes:
    0 - Success: OPRA fields populated
    1 - Failure: Insufficient liquidity or API error
    2 - Schema mismatch: Response missing required fields
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(
        description="Verify ORATS strikes/options endpoint returns OPRA liquidity fields"
    )
    parser.add_argument("symbol", help="Stock symbol (e.g., AAPL, SPY, TSLA)")
    parser.add_argument("--mode", choices=["delayed", "live", "live_derived"], default="delayed",
                        help="ORATS data mode (default: delayed)")
    parser.add_argument("--dte-min", type=int, default=30, help="Minimum DTE (default: 30)")
    parser.add_argument("--dte-max", type=int, default=45, help="Maximum DTE (default: 45)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--max-strikes", type=int, default=5, help="Max strikes per expiry (default: 5)")
    parser.add_argument("--max-expiries", type=int, default=3, help="Max expiries (default: 3)")
    
    args = parser.parse_args()
    symbol = args.symbol.upper()
    
    # Set ORATS_DATA_MODE environment variable
    os.environ["ORATS_DATA_MODE"] = args.mode
    
    print(f"\n{'='*70}")
    print(f"ORATS Strikes/Options Verification")
    print(f"{'='*70}")
    print(f"  Symbol:     {symbol}")
    print(f"  Mode:       {args.mode}")
    print(f"  DTE Range:  {args.dte_min} - {args.dte_max}")
    print(f"  Bounds:     {args.max_expiries} expiries × {args.max_strikes} strikes")
    print(f"  Timestamp:  {datetime.now().isoformat()}")
    print(f"{'='*70}\n")
    
    # Import pipeline (after setting env var)
    try:
        from app.core.options.orats_chain_pipeline import (
            OratsDataMode,
            OratsOpraModeError,
            fetch_base_chain,
            build_opra_symbols,
            fetch_enriched_contracts,
            merge_chain_and_liquidity,
            fetch_option_chain,
            check_liquidity_gate,
            get_strikes_options_param_name,
        )
    except ImportError as e:
        print(f"ERROR: Failed to import pipeline: {e}")
        return 1
    
    # Print selected base URL and param name
    base_url = OratsDataMode.get_base_url()
    print(f"[CONFIG] Base URL: {base_url}")
    
    # Check if mode supports OPRA fields
    if not OratsDataMode.supports_opra_fields():
        print(f"\n{'!'*70}")
        print(f"ERROR: Mode '{args.mode}' does NOT support OPRA liquidity fields!")
        print(f"       OPRA bid/ask/volume/OI will be NULL in this mode.")
        print(f"       Use --mode delayed or --mode live for OPRA data.")
        print(f"{'!'*70}\n")
        return 2
    
    # Probe for param name
    print(f"\n[PROBE] Detecting correct parameter name for strikes/options...")
    param_name = get_strikes_options_param_name()
    print(f"[PROBE] Selected param: {param_name}")
    
    # STEP 1: Fetch base chain
    print(f"\n[STEP 1] Fetching base chain from /strikes...")
    t0 = time.perf_counter()
    base_contracts, underlying_price, error = fetch_base_chain(
        symbol, args.dte_min, args.dte_max,
        max_strikes_per_expiry=args.max_strikes,
        max_expiries=args.max_expiries,
    )
    step1_latency = int((time.perf_counter() - t0) * 1000)
    
    if error:
        print(f"    ERROR: {error}")
        print(f"    HTTP latency: {step1_latency}ms")
        return 1
    
    puts = [c for c in base_contracts if c.option_type == "PUT"]
    calls = [c for c in base_contracts if c.option_type == "CALL"]
    
    print(f"    HTTP latency:     {step1_latency}ms")
    print(f"    Base chain count: {len(base_contracts)}")
    print(f"    - PUTs:           {len(puts)}")
    print(f"    - CALLs:          {len(calls)}")
    print(f"    Underlying:       ${underlying_price:.2f}" if underlying_price else "    Underlying:       N/A")
    
    if args.verbose and base_contracts:
        print(f"\n    Sample base contracts:")
        for c in base_contracts[:3]:
            print(f"      {c.option_type:4s} {c.expiration} ${c.strike:>8.2f} DTE={c.dte}")
    
    # STEP 2: Build OPRA symbols
    print(f"\n[STEP 2] Building OPRA symbols...")
    opra_map = build_opra_symbols(base_contracts)
    
    print(f"    OPRA symbols generated: {len(opra_map)}")
    
    if args.verbose and opra_map:
        print(f"\n    Sample OPRA symbols (first 5):")
        for i, (opra, contract) in enumerate(list(opra_map.items())[:5]):
            print(f"      {opra} → {contract.option_type} ${contract.strike:.2f}")
    
    # Select PUTs for enrichment (typical CSP workflow)
    opra_to_enrich = [opra for opra, c in opra_map.items() if c.option_type == "PUT"]
    print(f"    Enriching PUTs: {len(opra_to_enrich)} symbols")
    
    # STEP 3: Enrich with liquidity
    print(f"\n[STEP 3] Enriching with liquidity from /strikes/options...")
    t0 = time.perf_counter()
    try:
        enrichment_map = fetch_enriched_contracts(opra_to_enrich, require_opra_fields=True)
    except OratsOpraModeError as e:
        print(f"    ERROR: {e}")
        return 2
    step3_latency = int((time.perf_counter() - t0) * 1000)
    
    print(f"    HTTP latency:   {step3_latency}ms")
    print(f"    Enriched rows:  {len(enrichment_map)}")
    
    # Check row keys
    if enrichment_map:
        sample_opra = list(enrichment_map.keys())[0]
        sample_data = enrichment_map[sample_opra]
        row_keys = list(sample_data.keys())
        print(f"    Row keys:       {row_keys}")
    
    # SCHEMA VALIDATION: Check for required fields
    if len(enrichment_map) <= 1:
        print(f"\n{'!'*70}")
        print(f"FAIL: Response schema mismatch - only {len(enrichment_map)} row(s) returned")
        print(f"      Expected multiple OPRA-enriched contracts")
        print(f"{'!'*70}\n")
        return 2
    
    # STEP 4: Merge results
    print(f"\n[STEP 4] Merging chain and liquidity...")
    now_iso = datetime.utcnow().isoformat()
    merged = merge_chain_and_liquidity(base_contracts, enrichment_map, underlying_price, now_iso)
    
    # Compute stats
    with_bid = sum(1 for c in merged if c.bid is not None)
    with_ask = sum(1 for c in merged if c.ask is not None)
    with_oi = sum(1 for c in merged if c.open_interest is not None and c.open_interest > 0)
    with_vol = sum(1 for c in merged if c.volume is not None)
    with_delta = sum(1 for c in merged if c.delta is not None)
    with_liquidity = sum(1 for c in merged if c.has_valid_liquidity)
    
    total = len(merged) if merged else 1
    pct_bid = (with_bid / total * 100)
    pct_ask = (with_ask / total * 100)
    pct_oi = (with_oi / total * 100)
    pct_vol = (with_vol / total * 100)
    pct_delta = (with_delta / total * 100)
    pct_liquidity = (with_liquidity / total * 100)
    
    print(f"    Total merged:              {len(merged)}")
    print(f"    With bidPrice:             {with_bid} ({pct_bid:.1f}%)")
    print(f"    With askPrice:             {with_ask} ({pct_ask:.1f}%)")
    print(f"    With volume:               {with_vol} ({pct_vol:.1f}%)")
    print(f"    With openInterest > 0:     {with_oi} ({pct_oi:.1f}%)")
    print(f"    With delta:                {with_delta} ({pct_delta:.1f}%)")
    print(f"    With valid liquidity:      {with_liquidity} ({pct_liquidity:.1f}%)")
    
    # Sample valid contracts
    valid_puts = [c for c in merged if c.option_type == "PUT" and c.has_valid_liquidity]
    valid_calls = [c for c in merged if c.option_type == "CALL" and c.has_valid_liquidity]
    
    print(f"\n    Valid PUTs:  {len(valid_puts)}")
    print(f"    Valid CALLs: {len(valid_calls)}")
    
    # Print sample contracts
    if valid_puts:
        print(f"\n    Sample PUT contracts (top 3 by OI):")
        sorted_puts = sorted(valid_puts, key=lambda c: c.open_interest or 0, reverse=True)[:3]
        print(f"    {'OPRA Symbol':<24} {'Exp':<12} {'Strike':>8} {'Bid':>8} {'Ask':>8} {'OI':>8} {'Delta':>8}")
        print(f"    {'-'*24} {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
        for c in sorted_puts:
            delta_str = f"{c.delta:.3f}" if c.delta is not None else "N/A"
            print(f"    {c.opra_symbol:<24} {c.expiration.isoformat():<12} {c.strike:>8.2f} {c.bid:>8.2f} {c.ask:>8.2f} {c.open_interest:>8} {delta_str:>8}")
    
    # STEP 5: Liquidity gate check
    print(f"\n[STEP 5] Liquidity gate check...")
    
    # Build full chain result for gate check
    chain_result = fetch_option_chain(
        symbol, args.dte_min, args.dte_max,
        enrich_all=False,  # PUTs only for CSP
        max_strikes_per_expiry=args.max_strikes,
        max_expiries=args.max_expiries,
    )
    passed, reason = check_liquidity_gate(chain_result, min_valid_puts=3, min_valid_contracts=3)
    
    print(f"    Gate result: {reason}")
    
    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"  Mode:              {args.mode}")
    print(f"  Base URL:          {base_url}")
    print(f"  Param name:        {param_name}")
    print(f"  Base chain:        {len(base_contracts)} contracts")
    print(f"  OPRA symbols:      {len(opra_map)} generated")
    print(f"  Enriched:          {len(enrichment_map)} rows")
    print(f"  With liquidity:    {with_liquidity} contracts ({pct_liquidity:.1f}%)")
    print(f"  Valid PUTs:        {len(valid_puts)}")
    print(f"  Valid CALLs:       {len(valid_calls)}")
    print(f"  Liquidity gate:    {'PASS' if passed else 'FAIL'}")
    
    # Final verdict
    if passed and with_liquidity > 0:
        print(f"\n{'='*70}")
        print(f"✓ SUCCESS: {symbol} option chain has OPRA liquidity fields populated")
        print(f"  - bidPrice/askPrice:   {with_bid}/{with_ask} non-null")
        print(f"  - volume:              {with_vol} non-null")
        print(f"  - openInterest:        {with_oi} non-null (>0)")
        print(f"  - delta:               {with_delta} non-null")
        print(f"{'='*70}\n")
        return 0
    else:
        print(f"\n{'='*70}")
        print(f"✗ FAIL: {symbol} option chain has insufficient OPRA liquidity")
        if pct_liquidity == 0:
            print(f"  HINT: This may indicate:")
            print(f"    - Market is closed (try during market hours)")
            print(f"    - ORATS mode misconfigured (current: {args.mode})")
            print(f"    - API returning wrong data structure")
        print(f"{'='*70}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
