#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Run signal engine pipeline and save decision data for dashboard (Phase 6A).

Features:
- Pre-run health check for Theta Terminal
- Fallback to latest snapshot when live data unavailable
- Data source annotation in output JSON
- Snapshot cleanup (retention policy)
- decision_latest.json symlink/copy for easy access
- Test mode (--test) for diagnostics
"""

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

# Add project root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from app.core.settings import (
    get_output_dir,
    get_snapshot_max_files,
    get_snapshot_retention_days,
    is_fallback_enabled,
    load_config,
)
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
from app.data.theta_v3_provider import (
    ThetaV3Provider,
    DATA_SOURCE_LIVE,
    DATA_SOURCE_SNAPSHOT,
    DATA_SOURCE_UNAVAILABLE,
    OptionChainResult,
)
from app.execution.dry_run_executor import execute_dry_run
from app.execution.execution_gate import evaluate_execution_gate, ExecutionGateResult
from app.execution.execution_plan import build_execution_plan
from app.signals.engine import run_signal_engine
from app.signals.models import CCConfig, CSPConfig, SignalEngineConfig
from app.signals.scoring import ScoringConfig
from app.signals.selection import SelectionConfig


def _cleanup_old_snapshots(output_dir: Path, retention_days: int, max_files: int) -> Tuple[int, List[str]]:
    """Delete old decision_*.json files based on retention policy.
    
    Returns (deleted_count, deleted_filenames).
    """
    deleted: List[str] = []
    
    # Find all decision files (exclude decision_latest.json)
    decision_files = sorted(
        [f for f in output_dir.glob("decision_*.json") if f.name != "decision_latest.json"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,  # Newest first
    )
    
    if not decision_files:
        return 0, []
    
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days) if retention_days > 0 else None
    
    # Keep at most max_files (if set) and files newer than cutoff
    files_to_delete: List[Path] = []
    
    for i, f in enumerate(decision_files):
        keep = True
        
        # Check max_files limit
        if max_files > 0 and i >= max_files:
            keep = False
        
        # Check retention_days cutoff
        if cutoff and keep:
            file_mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if file_mtime < cutoff:
                keep = False
        
        if not keep:
            files_to_delete.append(f)
    
    for f in files_to_delete:
        try:
            f.unlink()
            deleted.append(f.name)
        except Exception as e:
            print(f"  Warning: Failed to delete {f.name}: {e}", file=sys.stderr)
    
    return len(deleted), deleted


def _create_latest_copy(output_file: Path) -> Optional[Path]:
    """Create decision_latest.json as a copy of the latest decision file.
    
    Returns the path to decision_latest.json or None on failure.
    """
    latest_path = output_file.parent / "decision_latest.json"
    try:
        shutil.copy2(output_file, latest_path)
        return latest_path
    except Exception as e:
        print(f"  Warning: Failed to create decision_latest.json: {e}", file=sys.stderr)
        return None


def _run_health_check(test_mode: bool = False) -> Tuple[bool, str, Optional[str]]:
    """Run Theta Terminal health check.
    
    Returns (healthy, message, data_source).
    data_source is None if healthy, or "snapshot" if fallback should be used.
    """
    provider = ThetaV3Provider()
    status = provider.health_check()
    provider.close()
    
    if test_mode:
        print(f"  Health check: {status.message}")
        if status.response_time_ms:
            print(f"  Response time: {status.response_time_ms:.1f}ms")
    
    if status.healthy:
        return True, status.message, None
    
    if is_fallback_enabled():
        return False, status.message, DATA_SOURCE_SNAPSHOT
    
    return False, status.message, None


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
        default=None,
        help="Output directory for decision JSON (default: from config.yaml)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: print diagnostics (endpoints hit, fallback status, symbol summary)",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable fallback to snapshot even if enabled in config",
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip cleanup of old decision files",
    )
    args = parser.parse_args()

    # Load configuration
    config = load_config()
    output_dir_str = args.output_dir or config.snapshots.output_dir
    test_mode = args.test
    
    if test_mode:
        print("=" * 60)
        print("ChakraOps Decision Pipeline - TEST MODE")
        print("=" * 60)
        print(f"  Theta Base URL: {config.theta.base_url}")
        print(f"  Fallback enabled: {config.theta.fallback_enabled and not args.no_fallback}")
        print(f"  Output dir: {output_dir_str}")
        print(f"  Retention: {config.snapshots.retention_days} days, max {config.snapshots.max_files} files")
        print("-" * 60)

    # Pre-run health check
    print("Checking Theta Terminal connectivity...")
    healthy, health_msg, fallback_data_source = _run_health_check(test_mode)
    
    # Track data source for output annotation
    data_source = DATA_SOURCE_LIVE
    
    if not healthy:
        print(f"  Theta Terminal: {health_msg}")
        if args.no_fallback or not is_fallback_enabled():
            print("ERROR: Theta Terminal not reachable and fallback is disabled.")
            print("  Start Theta Terminal or enable fallback_enabled in config.yaml")
            return 1
        print("  Fallback: Will use latest snapshot from disk")
        data_source = DATA_SOURCE_SNAPSHOT
    else:
        print(f"  Theta Terminal: OK")

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

    # Add data source annotation to snapshot
    decision_snapshot_dict = asdict(decision_snapshot)
    decision_snapshot_dict["data_source"] = data_source
    decision_snapshot_dict["pipeline_timestamp"] = datetime.now(timezone.utc).isoformat()

    # Prepare output data (preserve key ordering)
    output_data = {
        "decision_snapshot": decision_snapshot_dict,
        "execution_gate": asdict(gate_result),
        "execution_plan": asdict(execution_plan),
        "dry_run_result": asdict(dry_run_result),
        "metadata": {
            "data_source": data_source,
            "pipeline_timestamp": decision_snapshot_dict["pipeline_timestamp"],
            "theta_base_url": config.theta.base_url,
            "fallback_enabled": config.theta.fallback_enabled,
        },
    }

    # Output file: out/decision_<ISO_TIMESTAMP>.json
    # Note: Windows filenames cannot contain ":" so we make the ISO timestamp
    # filename-safe while keeping it human-readable.
    output_dir = Path(output_dir_str)
    output_dir.mkdir(parents=True, exist_ok=True)

    iso_ts = output_data["decision_snapshot"].get("as_of") or "unknown"
    safe_iso_ts = str(iso_ts).replace(":", "-")
    output_file = output_dir / f"decision_{safe_iso_ts}.json"

    # Write JSON file
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)
    
    # Create decision_latest.json copy
    latest_path = _create_latest_copy(output_file)
    if latest_path:
        print(f"  Latest: {latest_path}")
    
    # Cleanup old snapshots
    if not args.skip_cleanup:
        retention_days = get_snapshot_retention_days()
        max_files = get_snapshot_max_files()
        deleted_count, deleted_names = _cleanup_old_snapshots(output_dir, retention_days, max_files)
        if deleted_count > 0:
            print(f"  Cleanup: Deleted {deleted_count} old decision file(s)")
            if test_mode:
                for name in deleted_names[:5]:
                    print(f"    - {name}")
                if len(deleted_names) > 5:
                    print(f"    ... and {len(deleted_names) - 5} more")

    print(f"\nDecision pipeline complete:")
    print(f"  Data source: {data_source}")
    print(f"  Candidates: {result.stats['total_candidates']}")
    print(f"  Selected: {len(result.selected_signals) if result.selected_signals else 0}")
    print(f"  Gate allowed: {gate_result.allowed}")
    print(f"  Orders: {len(execution_plan.orders)}")
    print(f"  Output: {output_file}")
    
    # Test mode: additional diagnostics
    if test_mode:
        print("-" * 60)
        print("TEST MODE SUMMARY")
        print("-" * 60)
        
        # Symbol chain summary
        symbols_with = list(decision_snapshot.symbols_with_options or [])
        symbols_without = dict(decision_snapshot.symbols_without_options or {})
        print(f"\n[CHAIN INFO]")
        print(f"  Symbols with options: {len(symbols_with)}")
        print(f"  Symbols without options: {len(symbols_without)}")
        if symbols_with[:5]:
            print(f"    With chains: {', '.join(symbols_with[:5])}{'...' if len(symbols_with) > 5 else ''}")
        if list(symbols_without.keys())[:5]:
            reasons = [f"{k}({v})" for k, v in list(symbols_without.items())[:5]]
            print(f"    Missing chains: {', '.join(reasons)}{'...' if len(symbols_without) > 5 else ''}")
        
        # Candidate scoring summary
        scored = result.scored_candidates or []
        selected = result.selected_signals or []
        print(f"\n[SCORING INFO]")
        print(f"  Total candidates: {len(result.candidates)}")
        print(f"  Scored candidates: {len(scored)}")
        print(f"  Selected candidates: {len(selected)}")
        
        # Show top 5 candidates with scores
        if scored[:5]:
            print(f"\n  Top 5 Scored Candidates:")
            for sc in scored[:5]:
                c = sc.candidate
                s = sc.score
                premium = c.mid or ((c.bid or 0) + (c.ask or 0)) / 2 if c.bid and c.ask else 0
                print(f"    #{sc.rank}: {c.symbol} {c.signal_type.value} ${c.strike} exp={c.expiry}")
                print(f"        Premium: ${premium:.2f}  DTE: {(c.expiry.toordinal() - datetime.now().date().toordinal()) if hasattr(c.expiry, 'toordinal') else 'N/A'}")
                print(f"        Score: {s.total:.4f}")
                # Show score components
                comp_str = ", ".join([f"{comp.name.replace('_score', '')}={comp.value:.2f}*{comp.weight}" for comp in s.components])
                print(f"        Components: {comp_str}")
        
        # Show selected signals
        if selected[:5]:
            print(f"\n  Selected Signals (passed gate):")
            for sel in selected[:5]:
                c = sel.scored.candidate
                s = sel.scored.score
                print(f"    {c.symbol} {c.signal_type.value} ${c.strike} exp={c.expiry} score={s.total:.4f} reason={sel.selection_reason}")
        
        # Show rejection reasons from exclusions
        exclusion_codes = {}
        for excl in result.exclusions:
            code = excl.code
            exclusion_codes[code] = exclusion_codes.get(code, 0) + 1
        
        if exclusion_codes:
            print(f"\n[REJECTION SUMMARY]")
            print(f"  Total exclusions: {len(result.exclusions)}")
            for code, count in sorted(exclusion_codes.items(), key=lambda x: -x[1])[:10]:
                print(f"    {code}: {count}")
        
        # Data source
        print(f"\n[DATA SOURCE]")
        print(f"  Source: {data_source}")
        if data_source == DATA_SOURCE_SNAPSHOT:
            print("    (Live data unavailable, used fallback snapshot)")
        
        print("=" * 60)

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
