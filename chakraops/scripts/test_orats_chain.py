#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Diagnostic script to test ORATS Live Data and validate strategy criteria.

Uses ORATS provider for expirations and chain. Strategy filters:
- DTE window (7-45 days default)
- Delta range (for CSP: -0.30 to -0.10)
- Credit thresholds
- Bid/ask spread limits

Usage:
    # Basic diagnostic (expirations + chain)
    python scripts/test_orats_chain.py AAPL

    # Full strategy validation with filters
    python scripts/test_orats_chain.py AAPL --validate-strategy

    # Custom criteria
    python scripts/test_orats_chain.py AAPL --validate-strategy --min-delta -0.30 --max-delta -0.10 --min-credit 0.50

Requires: ORATS_API_TOKEN in environment or .env file.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

# Load .env so ORATS_API_TOKEN is available
from dotenv import load_dotenv
load_dotenv(repo_root / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test ORATS Live Data and validate strategy criteria"
    )
    parser.add_argument("symbol", help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--dte-min", type=int, default=7, help="Minimum DTE (default: 7)")
    parser.add_argument("--dte-max", type=int, default=45, help="Maximum DTE (default: 45)")
    parser.add_argument("--validate-strategy", "-v", action="store_true",
                        help="Run CSP candidate filtering")
    parser.add_argument("--min-delta", type=float, default=-0.30, help="Min put delta (default: -0.30)")
    parser.add_argument("--max-delta", type=float, default=-0.10, help="Max put delta (default: -0.10)")
    parser.add_argument("--min-credit", type=float, default=0.50, help="Min bid/credit (default: 0.50)")
    parser.add_argument("--max-spread-pct", type=float, default=20.0, help="Max bid-ask spread %% (default: 20)")
    parser.add_argument("--min-bid", type=float, default=0.10, help="Min bid (default: 0.10)")
    args = parser.parse_args()

    if not (os.getenv("ORATS_API_TOKEN") or "").strip():
        print("ORATS_API_TOKEN is not set. Set it to run this script.")
        return 1

    from app.data.options_chain_provider import OratsOptionsChainProvider

    symbol = (args.symbol or "").upper()
    if not symbol:
        print("Invalid symbol.")
        return 1

    provider = OratsOptionsChainProvider()

    # Health
    status = provider.healthcheck()
    if not status.get("ok"):
        print("ORATS health check failed:", status.get("message", "Unknown"))
        return 1
    print("ORATS health:", status.get("message"))

    # Expirations
    print(f"\n[1] Expirations for {symbol}...")
    expirations = provider.get_expirations(symbol)
    if not expirations:
        print("  No expirations returned.")
        return 1
    print(f"  Found {len(expirations)} expirations")
    print(f"  First 5: {[d.isoformat() for d in expirations[:5]]}")

    if not args.validate_strategy:
        print("\nDone. Use --validate-strategy to run CSP candidate filtering.")
        return 0

    # Full chain (DTE window)
    print(f"\n[2] Full chain (DTE {args.dte_min}-{args.dte_max})...")
    full = provider.get_full_chain(symbol, dte_min=args.dte_min, dte_max=args.dte_max)
    contracts = full.get("contracts") or []
    puts = [c for c in contracts if (c.get("right") or "").upper() == "P"]
    calls = [c for c in contracts if (c.get("right") or "").upper() == "C"]
    print(f"  Total contracts: {len(contracts)} (PUTs: {len(puts)}, CALLs: {len(calls)})")

    if not puts:
        print("  No PUTs in chain.")
        return 0

    # CSP candidate filtering
    min_delta = args.min_delta
    max_delta = args.max_delta
    min_credit = args.min_credit
    max_spread_pct = args.max_spread_pct
    min_bid = args.min_bid
    rejection_reasons: Dict[str, int] = {
        "no_bid": 0,
        "bid_too_low": 0,
        "spread_too_wide": 0,
        "delta_out_of_range": 0,
        "credit_too_low": 0,
        "no_delta": 0,
    }
    csp_candidates: List[Dict[str, Any]] = []

    for c in puts:
        bid = c.get("bid")
        ask = c.get("ask")
        delta = c.get("delta")
        if bid is None or bid <= 0:
            rejection_reasons["no_bid"] += 1
            continue
        if bid < min_bid:
            rejection_reasons["bid_too_low"] += 1
            continue
        if ask and ask > 0 and bid > 0:
            spread_pct = ((ask - bid) / bid) * 100
            if spread_pct > max_spread_pct:
                rejection_reasons["spread_too_wide"] += 1
                continue
        if delta is not None:
            if not (min_delta <= delta <= max_delta):
                rejection_reasons["delta_out_of_range"] += 1
                continue
        else:
            rejection_reasons["no_delta"] += 1
        if bid < min_credit:
            rejection_reasons["credit_too_low"] += 1
            continue
        csp_candidates.append(c)

    print(f"\n[CSP CANDIDATE FILTERING]")
    print(f"  PUTs evaluated: {len(puts)}")
    print(f"  CSP candidates: {len(csp_candidates)}")
    print("  Rejections:")
    for reason, count in rejection_reasons.items():
        if count > 0:
            print(f"    - {reason}: {count}")
    if csp_candidates:
        print("\n  Sample candidates:")
        for c in csp_candidates[:5]:
            strike = c.get("strike", 0)
            exp = c.get("expiration", "")
            bid = c.get("bid", 0)
            ask = c.get("ask", 0)
            delta = c.get("delta")
            delta_str = f"{delta:.3f}" if delta is not None else "N/A"
            print(f"    {symbol} PUT ${strike:.0f} exp={exp} bid=${bid:.2f} ask=${ask:.2f} delta={delta_str}")
    else:
        print("  No CSP candidates. Consider relaxing min_credit, delta range, or max_spread_pct.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
