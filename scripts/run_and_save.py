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

from app.core.persistence import get_enabled_symbols
from app.core.market.stock_universe import StockUniverseManager
from app.core.options.options_availability import (
    DiagnosticsOptionsChainProvider,
    OptionsAvailabilityRecorder,
)
from app.core.gates.options_data_health import evaluate_options_data_health
from app.data.options_chain_provider import (
    FallbackWeeklyExpirationsProvider,
    ThetaDataOptionsChainProvider,
)
from app.data.stock_snapshot_provider import StockSnapshotProvider
from app.execution.dry_run_executor import execute_dry_run
from app.execution.execution_gate import evaluate_execution_gate, ExecutionGateResult
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

    # Initialize providers (optional fallback: OPTIONS_FALLBACK_WEEKLY_EXPIRATIONS=1)
    snapshot_provider = StockSnapshotProvider()
    options_provider_inner = ThetaDataOptionsChainProvider()
    options_provider_inner = FallbackWeeklyExpirationsProvider(options_provider_inner)
    options_recorder = OptionsAvailabilityRecorder()
    options_provider = DiagnosticsOptionsChainProvider(options_provider_inner, options_recorder)

    # Load universe from DB (symbol_universe where enabled=1). Fail loudly if empty.
    enabled_symbols = get_enabled_symbols()
    if not enabled_symbols:
        print("ERROR: Zero enabled symbols in symbol_universe. Import universe from CSV first.")
        print("  Example: python -c \"from app.db.universe_import import import_universe_from_csv; import_universe_from_csv()\"")
        return 1
    print(f"Symbols from DB (enabled=1): {len(enabled_symbols)}")

    universe_manager = StockUniverseManager(snapshot_provider, symbols_from_db=enabled_symbols)
    eligible_stocks = universe_manager.get_eligible_stocks()

    # Apply limit if specified
    if args.limit:
        eligible_stocks = eligible_stocks[: args.limit]

    print(f"Processing {len(eligible_stocks)} symbols (from DB universe, after filters)...")

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

    # Run signal engine (with options diagnostics recorder)
    print("Running signal engine...")
    result = run_signal_engine(
        stock_snapshots=eligible_stocks,
        options_chain_provider=options_provider,
        base_config=base_config,
        csp_config=csp_config,
        cc_config=cc_config,
        universe_id_or_hash="db_universe",
        options_availability_recorder=options_recorder,
    )

    # Extract decision snapshot
    decision_snapshot = result.decision_snapshot
    if decision_snapshot is None:
        print("ERROR: Decision snapshot is None")
        return 1

    # Options data health gate: block only if zero symbols have valid options
    symbols_with_options = list(decision_snapshot.symbols_with_options or [])
    symbols_without_options = dict(decision_snapshot.symbols_without_options or {})
    options_health = evaluate_options_data_health(symbols_with_options, symbols_without_options)
    if options_health.allowed:
        print(f"  Partial universe: {options_health.valid_symbols_count} eligible, {options_health.excluded_count} excluded (missing options)")
    else:
        print(f"  Options data health: BLOCKED (0 symbols with options, {options_health.excluded_count} excluded)")

    # Evaluate execution gate
    gate_result = evaluate_execution_gate(decision_snapshot)

    # Merge options data health: if options health blocks, gate is blocked with clear reason
    if not options_health.allowed:
        combined_reasons = list(gate_result.reasons or []) + options_health.reasons
        gate_result = ExecutionGateResult(allowed=False, reasons=combined_reasons)

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

    # Slack: only notify on gate state change, advisory severity change, or manual send (UX requirement).
    # Persist last state next to output dir so we do not fire on every refresh/run.
    slack_state_path = output_dir / ".slack_state.json"
    last_gate_allowed = None
    last_drift_severity = None
    if slack_state_path.exists():
        try:
            with open(slack_state_path) as f:
                state = json.load(f)
            last_gate_allowed = state.get("last_gate_allowed")
            last_drift_severity = state.get("last_drift_severity")
        except (json.JSONDecodeError, OSError):
            pass
    try:
        from app.notifications.slack_notifier import send_decision_alert
        sent = send_decision_alert(
            snapshot=decision_snapshot,
            gate_result=gate_result,
            execution_plan=execution_plan,
            decision_file_path=output_file,
            last_gate_allowed=last_gate_allowed,
            last_drift_severity=last_drift_severity,
        )
        # Persist current state so next run only notifies on change
        try:
            with open(slack_state_path, "w") as f:
                json.dump(
                    {
                        "last_gate_allowed": gate_result.allowed,
                        "last_drift_severity": last_drift_severity,
                    },
                    f,
                    indent=2,
                )
        except OSError:
            pass
        if sent:
            print(f"  Slack alert sent")
        else:
            print(f"  Slack skipped (no gate/severity change)")
    except Exception as e:
        # Slack failure must NOT break pipeline
        print(f"  Slack alert failed (non-blocking): {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
