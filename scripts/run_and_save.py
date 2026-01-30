#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Run signal engine pipeline and save decision data for dashboard.

Features:
- Pre-run health check for Theta Terminal
- Fallback to latest snapshot when live data unavailable
- Data source annotation in output JSON
- Snapshot cleanup (retention policy)
- decision_latest.json copy for easy access
- Test mode (--test) for diagnostics
- Realtime mode (--realtime) for continuous updates during market hours
- Daily retention policy to keep only latest snapshot per day
"""

import argparse
import json
import shutil
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

# Add project root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from app.core.settings import (
    get_output_dir,
    get_snapshot_max_files,
    get_snapshot_retention_days,
    get_realtime_refresh_interval,
    get_realtime_end_time,
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
)
from app.execution.dry_run_executor import execute_dry_run
from app.execution.execution_gate import evaluate_execution_gate, ExecutionGateResult
from app.execution.execution_plan import build_execution_plan
from app.signals.engine import run_signal_engine
from app.signals.models import CCConfig, CSPConfig, SignalEngineConfig
from app.signals.scoring import ScoringConfig
from app.signals.selection import SelectionConfig


def enforce_daily_retention(output_dir: Path, max_days: int = 7) -> Tuple[int, List[str]]:
    """Enforce daily retention policy.
    
    Keeps only:
    - decision_latest.json (always)
    - sample_decision*.json (always)
    - One snapshot per day for the last max_days
    - Deletes duplicates for the same day, keeping newest
    
    Returns (deleted_count, deleted_filenames).
    """
    deleted: List[str] = []
    
    # Find all decision files (exclude special files)
    special_files = {"decision_latest.json", "sample_decision.json", "sample_decision_rich.json"}
    decision_files = sorted(
        [f for f in output_dir.glob("decision_*.json") if f.name not in special_files],
        key=lambda p: p.stat().st_mtime,
        reverse=True,  # Newest first
    )
    
    if not decision_files:
        return 0, []
    
    # Group files by date
    files_by_date: Dict[str, List[Path]] = {}
    for f in decision_files:
        try:
            file_date = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
            if file_date not in files_by_date:
                files_by_date[file_date] = []
            files_by_date[file_date].append(f)
        except OSError:
            continue
    
    # Determine cutoff date
    cutoff_date = (date.today() - timedelta(days=max_days)).strftime("%Y-%m-%d")
    
    files_to_delete: List[Path] = []
    
    for file_date, files in files_by_date.items():
        if file_date < cutoff_date:
            # Delete all files older than retention period
            files_to_delete.extend(files)
        else:
            # Keep only the newest file for each day (first in sorted list)
            if len(files) > 1:
                files_to_delete.extend(files[1:])  # Delete all except newest
    
    for f in files_to_delete:
        try:
            f.unlink()
            deleted.append(f.name)
        except Exception as e:
            print(f"  Warning: Failed to delete {f.name}: {e}", file=sys.stderr)
    
    return len(deleted), deleted


def _cleanup_old_snapshots(output_dir: Path, retention_days: int, max_files: int) -> Tuple[int, List[str]]:
    """Delete old decision_*.json files based on retention policy.
    
    Returns (deleted_count, deleted_filenames).
    """
    deleted: List[str] = []
    
    special_files = {"decision_latest.json", "sample_decision.json", "sample_decision_rich.json"}
    decision_files = sorted(
        [f for f in output_dir.glob("decision_*.json") if f.name not in special_files],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    
    if not decision_files:
        return 0, []
    
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days) if retention_days > 0 else None
    
    files_to_delete: List[Path] = []
    
    for i, f in enumerate(decision_files):
        keep = True
        
        if max_files > 0 and i >= max_files:
            keep = False
        
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
    """Create decision_latest.json as a copy of the latest decision file."""
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


def run_pipeline(
    args: argparse.Namespace,
    config: Any,
    test_mode: bool = False,
    realtime_mode: bool = False,
) -> Tuple[int, Optional[Path]]:
    """Run a single pipeline iteration.
    
    Returns (exit_code, output_file_path).
    """
    output_dir_str = args.output_dir or config.snapshots.output_dir
    
    if test_mode:
        print("-" * 60)
        print(f"  Theta Base URL: {config.theta.base_url}")
        print(f"  Fallback enabled: {config.theta.fallback_enabled and not args.no_fallback}")
        print(f"  Output dir: {output_dir_str}")
        print("-" * 60)
    
    # Health check
    healthy, health_msg, fallback_data_source = _run_health_check(test_mode)
    data_source = DATA_SOURCE_LIVE
    
    if not healthy:
        print(f"  Theta Terminal: {health_msg}")
        if args.no_fallback or not is_fallback_enabled():
            print("ERROR: Theta Terminal not reachable and fallback disabled.")
            return 1, None
        print("  Fallback: Using latest snapshot")
        data_source = DATA_SOURCE_SNAPSHOT
    else:
        if not realtime_mode:
            print("  Theta Terminal: OK")
    
    # Initialize providers
    snapshot_provider = StockSnapshotProvider()
    options_provider_inner = ThetaDataOptionsChainProvider()
    options_provider_inner = FallbackWeeklyExpirationsProvider(options_provider_inner)
    options_recorder = OptionsAvailabilityRecorder()
    options_provider = DiagnosticsOptionsChainProvider(options_provider_inner, options_recorder)
    
    # Load universe
    enabled_symbols = get_enabled_symbols()
    if not enabled_symbols:
        print("ERROR: Zero enabled symbols in symbol_universe.")
        return 1, None
    
    if not realtime_mode:
        print(f"Symbols from DB: {len(enabled_symbols)}")
    
    universe_manager = StockUniverseManager(snapshot_provider, symbols_from_db=enabled_symbols)
    eligible_stocks = universe_manager.get_eligible_stocks()
    
    if args.limit:
        eligible_stocks = eligible_stocks[:args.limit]
    
    if not realtime_mode:
        print(f"Processing {len(eligible_stocks)} symbols...")
    
    # Configuration
    scoring_config = ScoringConfig(
        premium_weight=1.0, dte_weight=1.0, spread_weight=1.0,
        otm_weight=1.0, liquidity_weight=1.0,
    )
    
    selection_config = SelectionConfig(
        max_total=10, max_per_symbol=2, max_per_signal_type=None, min_score=0.0,
    )
    
    base_config = SignalEngineConfig(
        dte_min=30, dte_max=45, min_bid=0.01, min_open_interest=100,
        max_spread_pct=20.0, scoring_config=scoring_config, selection_config=selection_config,
    )
    
    csp_config = CSPConfig(otm_pct_min=0.05, otm_pct_max=0.15)
    cc_config = CCConfig(otm_pct_min=0.02, otm_pct_max=0.10)
    
    # Run engine
    result = run_signal_engine(
        stock_snapshots=eligible_stocks,
        options_chain_provider=options_provider,
        base_config=base_config,
        csp_config=csp_config,
        cc_config=cc_config,
        universe_id_or_hash="db_universe",
        options_availability_recorder=options_recorder,
    )
    
    decision_snapshot = result.decision_snapshot
    if decision_snapshot is None:
        print("ERROR: Decision snapshot is None")
        return 1, None
    
    # Options health gate
    symbols_with_options = list(decision_snapshot.symbols_with_options or [])
    symbols_without_options = dict(decision_snapshot.symbols_without_options or {})
    options_health = evaluate_options_data_health(symbols_with_options, symbols_without_options)
    
    if not realtime_mode:
        if options_health.allowed:
            print(f"  Partial universe: {options_health.valid_symbols_count} eligible, {options_health.excluded_count} excluded")
        else:
            print(f"  Options health: BLOCKED (0 symbols with options)")
    
    # Execution gate
    gate_result = evaluate_execution_gate(decision_snapshot)
    
    if not options_health.allowed:
        combined_reasons = list(gate_result.reasons or []) + options_health.reasons
        gate_result = ExecutionGateResult(allowed=False, reasons=combined_reasons)
    
    execution_plan = build_execution_plan(decision_snapshot, gate_result)
    dry_run_result = execute_dry_run(execution_plan)
    
    # Prepare output
    decision_snapshot_dict = asdict(decision_snapshot)
    decision_snapshot_dict["data_source"] = data_source
    decision_snapshot_dict["pipeline_timestamp"] = datetime.now(timezone.utc).isoformat()
    
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
    
    # Save file
    output_dir = Path(output_dir_str)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    iso_ts = output_data["decision_snapshot"].get("as_of") or "unknown"
    safe_iso_ts = str(iso_ts).replace(":", "-")
    output_file = output_dir / f"decision_{safe_iso_ts}.json"
    
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)
    
    # Create latest copy
    latest_path = _create_latest_copy(output_file)
    
    # Cleanup
    if not args.skip_cleanup:
        retention_days = get_snapshot_retention_days()
        max_files = get_snapshot_max_files()
        deleted_count, _ = _cleanup_old_snapshots(output_dir, retention_days, max_files)
        
        # Also enforce daily retention
        daily_deleted, _ = enforce_daily_retention(output_dir, max_days=retention_days)
        
        if not realtime_mode and (deleted_count > 0 or daily_deleted > 0):
            print(f"  Cleanup: Deleted {deleted_count + daily_deleted} old file(s)")
    
    if not realtime_mode:
        print(f"\nPipeline complete:")
        print(f"  Data source: {data_source}")
        print(f"  Candidates: {result.stats['total_candidates']}")
        print(f"  Selected: {len(result.selected_signals) if result.selected_signals else 0}")
        print(f"  Gate: {'ALLOWED' if gate_result.allowed else 'BLOCKED'}")
        print(f"  Orders: {len(execution_plan.orders)}")
        print(f"  Output: {output_file}")
    else:
        ts = datetime.now().strftime("%H:%M:%S")
        candidates = result.stats['total_candidates']
        selected = len(result.selected_signals) if result.selected_signals else 0
        print(f"[{ts}] Candidates: {candidates}, Selected: {selected}, Gate: {'✓' if gate_result.allowed else '✗'}")
    
    return 0, output_file


def run_realtime_loop(args: argparse.Namespace, config: Any) -> int:
    """Run pipeline in realtime mode until market close.
    
    Continuously refreshes data at the specified interval.
    """
    # Get realtime settings - command line overrides config
    refresh_interval = args.interval if args.interval else get_realtime_refresh_interval()
    end_time_str = get_realtime_end_time()
    
    print("=" * 60)
    print("ChakraOps Decision Pipeline - REALTIME MODE")
    print("=" * 60)
    print(f"  Refresh interval: {refresh_interval}s")
    print(f"  End time: {end_time_str}")
    print(f"  Press Ctrl+C to stop")
    print("=" * 60)
    
    iteration = 0
    last_output_file: Optional[Path] = None
    
    try:
        while True:
            iteration += 1
            
            # Check end time
            now = datetime.now()
            try:
                end_h, end_m, end_s = map(int, end_time_str.split(":"))
                end_time = now.replace(hour=end_h, minute=end_m, second=end_s, microsecond=0)
                if now >= end_time:
                    print(f"\n[{now.strftime('%H:%M:%S')}] Market close reached, stopping realtime mode")
                    break
            except ValueError:
                pass  # Invalid end_time format, continue indefinitely
            
            # Run pipeline
            exit_code, output_file = run_pipeline(args, config, test_mode=False, realtime_mode=True)
            
            if exit_code != 0:
                print(f"  Pipeline iteration {iteration} failed with code {exit_code}")
            else:
                last_output_file = output_file
            
            # Sleep until next iteration
            time.sleep(refresh_interval)
    
    except KeyboardInterrupt:
        print("\n\nRealtime mode interrupted by user")
    
    # Write final snapshot with _end suffix
    if last_output_file:
        final_name = f"decision_{date.today().isoformat()}_end.json"
        final_path = last_output_file.parent / final_name
        try:
            shutil.copy2(last_output_file, final_path)
            print(f"Final snapshot: {final_path}")
        except Exception as e:
            print(f"Warning: Failed to create final snapshot: {e}")
    
    print("Realtime mode ended")
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run full decision pipeline and save unified decision artifact"
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit symbols")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    parser.add_argument("--test", action="store_true", help="Test mode with diagnostics")
    parser.add_argument("--no-fallback", action="store_true", help="Disable fallback")
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip cleanup")
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Realtime mode: continuously update until market close"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Refresh interval in seconds for realtime mode (default: 60)"
    )
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    if args.realtime:
        return run_realtime_loop(args, config)
    
    if args.test:
        print("=" * 60)
        print("ChakraOps Decision Pipeline - TEST MODE")
        print("=" * 60)
    
    print("Checking Theta Terminal connectivity...")
    
    exit_code, output_file = run_pipeline(args, config, test_mode=args.test)
    
    if exit_code != 0:
        return exit_code
    
    # Test mode diagnostics
    if args.test and output_file:
        print("-" * 60)
        print("TEST MODE COMPLETE")
        print("-" * 60)
    
    # Slack notification (only on gate state change)
    output_dir = Path(args.output_dir or config.snapshots.output_dir)
    slack_state_path = output_dir / ".slack_state.json"
    
    if output_file:
        with open(output_file, "r") as f:
            output_data = json.load(f)
        
        gate_result = output_data.get("execution_gate", {})
        decision_snapshot = output_data.get("decision_snapshot", {})
        
        last_gate_allowed = None
        if slack_state_path.exists():
            try:
                with open(slack_state_path) as f:
                    state = json.load(f)
                last_gate_allowed = state.get("last_gate_allowed")
            except (json.JSONDecodeError, OSError):
                pass
        
        try:
            from app.notifications.slack_notifier import send_decision_alert
            sent = send_decision_alert(
                snapshot=decision_snapshot,
                gate_result=gate_result,
                execution_plan=output_data.get("execution_plan", {}),
                decision_file_path=output_file,
                last_gate_allowed=last_gate_allowed,
            )
            
            try:
                with open(slack_state_path, "w") as f:
                    json.dump({"last_gate_allowed": gate_result.get("allowed")}, f)
            except OSError:
                pass
            
            if sent:
                print("  Slack alert sent")
            else:
                print("  Slack skipped (no change)")
        except Exception as e:
            print(f"  Slack failed: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
