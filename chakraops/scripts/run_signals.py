#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""CLI script to run signal engine on Phase 2 universe."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from app.core.market.stock_universe import StockUniverseManager
from app.data.options_chain_provider import OratsOptionsChainProvider
from app.data.stock_snapshot_provider import StockSnapshotProvider
from app.signals.engine import run_signal_engine
from app.signals.models import CCConfig, CSPConfig, SignalEngineConfig


def serialize_result(result) -> dict:
    """Serialize SignalRunResult to JSON-serializable dict."""
    from app.signals.models import SignalType

    def serialize_candidate(c):
        """Serialize SignalCandidate to dict."""
        return {
            "symbol": c.symbol,
            "signal_type": c.signal_type.value,
            "as_of": c.as_of.isoformat(),
            "underlying_price": c.underlying_price,
            "expiry": c.expiry.isoformat(),
            "strike": c.strike,
            "option_right": c.option_right,
            "bid": c.bid,
            "ask": c.ask,
            "mid": c.mid,
            "volume": c.volume,
            "open_interest": c.open_interest,
            "delta": c.delta,
            "prob_otm": c.prob_otm,
            "iv_rank": c.iv_rank,
            "iv": c.iv,
            "annualized_yield": c.annualized_yield,
            "raw_yield": c.raw_yield,
            "max_profit": c.max_profit,
            "collateral": c.collateral,
            "explanation": [
                {
                    "code": e.code,
                    "message": e.message,
                    "data": e.data,
                }
                for e in c.explanation
            ],
            "exclusions": [
                {
                    "code": ex.code,
                    "message": ex.message,
                    "data": ex.data,
                }
                for ex in c.exclusions
            ],
        }

    def serialize_exclusion(ex):
        """Serialize ExclusionReason to dict."""
        return {
            "code": ex.code,
            "message": ex.message,
            "data": ex.data,
        }

    return {
        "as_of": result.as_of.isoformat(),
        "universe_id_or_hash": result.universe_id_or_hash,
        "configs": result.configs,
        "candidates": [serialize_candidate(c) for c in result.candidates],
        "exclusions": [serialize_exclusion(ex) for ex in result.exclusions],
        "stats": result.stats,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run signal engine on Phase 2 universe")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of symbols to process (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="out",
        help="Output directory for JSON files (default: out)",
    )
    args = parser.parse_args()

    # Initialize providers
    snapshot_provider = StockSnapshotProvider()
    options_provider = OratsOptionsChainProvider()

    # Load Phase 2 universe
    universe_manager = StockUniverseManager(snapshot_provider)
    eligible_stocks = universe_manager.get_eligible_stocks()

    # Apply limit if specified
    if args.limit:
        eligible_stocks = eligible_stocks[: args.limit]

    print(f"Processing {len(eligible_stocks)} symbols from Phase 2 universe...")

    # Default configurations
    base_config = SignalEngineConfig(
        dte_min=30,
        dte_max=45,
        min_bid=0.01,
        min_open_interest=100,
        max_spread_pct=20.0,
    )

    csp_config = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)
    cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)

    # Run signal engine
    result = run_signal_engine(
        stock_snapshots=eligible_stocks,
        options_chain_provider=options_provider,
        base_config=base_config,
        csp_config=csp_config,
        cc_config=cc_config,
        universe_id_or_hash="phase2_default",
    )

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate output filename
    as_of_str = result.as_of.strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"signals_{as_of_str}.json"

    # Serialize and write JSON
    result_dict = serialize_result(result)
    with open(output_file, "w") as f:
        json.dump(result_dict, f, indent=2)

    print(f"Signal engine run complete:")
    print(f"  Candidates: {result.stats['total_candidates']} (CSP: {result.stats['csp_candidates']}, CC: {result.stats['cc_candidates']})")
    print(f"  Exclusions: {result.stats['total_exclusions']}")
    print(f"  Output: {output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
