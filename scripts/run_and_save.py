#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Run signal engine pipeline and save decision data for dashboard (Phase 6A)."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

# Add project root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from app.core.market.stock_universe import StockUniverseManager
from app.data.options_chain_provider import ThetaDataOptionsChainProvider
from app.data.stock_snapshot_provider import StockSnapshotProvider
from app.execution.dry_run_executor import execute_dry_run
from app.execution.execution_gate import evaluate_execution_gate
from app.execution.execution_plan import build_execution_plan
from app.signals.engine import run_signal_engine
from app.signals.models import CCConfig, CSPConfig, SignalEngineConfig
from app.signals.scoring import ScoringConfig
from app.signals.selection import SelectionConfig


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run full decision pipeline and save unified decision artifact"
    )
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
        help="Output directory for decision JSON (default: out/)",
    )
    args = parser.parse_args()

    # Initialize providers
    snapshot_provider = StockSnapshotProvider()
    options_provider = ThetaDataOptionsChainProvider()

    # Load Phase 2 universe
    universe_manager = StockUniverseManager(snapshot_provider)
    eligible_stocks = universe_manager.get_eligible_stocks()

    # Apply limit if specified
    if args.limit:
        eligible_stocks = eligible_stocks[: args.limit]

    print(f"Processing {len(eligible_stocks)} symbols from Phase 2 universe...")

    # Scoring configuration
    scoring_config = ScoringConfig(
        premium_weight=1.0,
        dte_weight=1.0,
        spread_weight=1.0,
        otm_weight=1.0,
        liquidity_weight=1.0,
    )

    # Selection configuration
    selection_config = SelectionConfig(
        max_total=10,
        max_per_symbol=2,
        max_per_signal_type=None,
        min_score=0.0,
    )

    # Base engine configuration
    base_config = SignalEngineConfig(
        dte_min=30,
        dte_max=45,
        min_bid=0.01,
        min_open_interest=100,
        max_spread_pct=20.0,
        scoring_config=scoring_config,
        selection_config=selection_config,
    )

    csp_config = CSPConfig(
        otm_pct_min=0.05,
        otm_pct_max=0.15,
        delta_min=None,
        delta_max=None,
    )

    cc_config = CCConfig(
        otm_pct_min=0.02,
        otm_pct_max=0.10,
        delta_min=None,
        delta_max=None,
    )

    # Run signal engine
    print("Running signal engine...")
    result = run_signal_engine(
        stock_snapshots=eligible_stocks,
        options_chain_provider=options_provider,
        base_config=base_config,
        csp_config=csp_config,
        cc_config=cc_config,
        universe_id_or_hash="phase2_default",
    )

    # Extract decision snapshot
    decision_snapshot = result.decision_snapshot
    if decision_snapshot is None:
        print("ERROR: Decision snapshot is None")
        return 1

    # Evaluate execution gate
    gate_result = evaluate_execution_gate(decision_snapshot)

    # Build execution plan
    execution_plan = build_execution_plan(decision_snapshot, gate_result)

    # Execute dry-run
    dry_run_result = execute_dry_run(execution_plan)

    # Prepare output data (preserve key ordering)
    output_data = {
        "decision_snapshot": asdict(decision_snapshot),
        "execution_gate": asdict(gate_result),
        "execution_plan": asdict(execution_plan),
        "dry_run_result": asdict(dry_run_result),
    }

    # Output file: out/decision_<ISO_TIMESTAMP>.json
    # Note: Windows filenames cannot contain ":" so we make the ISO timestamp
    # filename-safe while keeping it human-readable.
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    iso_ts = output_data["decision_snapshot"].get("as_of") or "unknown"
    safe_iso_ts = str(iso_ts).replace(":", "-")
    output_file = output_dir / f"decision_{safe_iso_ts}.json"

    # Write JSON file
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nDecision pipeline complete:")
    print(f"  Candidates: {result.stats['total_candidates']}")
    print(f"  Selected: {len(result.selected_signals) if result.selected_signals else 0}")
    print(f"  Gate allowed: {gate_result.allowed}")
    print(f"  Orders: {len(execution_plan.orders)}")
    print(f"  Output: {output_file}")

    # Send Slack alert (Phase 7.1) - non-blocking, failures don't break pipeline
    try:
        from app.notifications.slack_notifier import send_decision_alert
        send_decision_alert(
            snapshot=decision_snapshot,
            gate_result=gate_result,
            execution_plan=execution_plan,
            decision_file_path=output_file,
        )
        print(f"  Slack alert sent")
    except Exception as e:
        # Slack failure must NOT break pipeline
        print(f"  Slack alert failed (non-blocking): {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
