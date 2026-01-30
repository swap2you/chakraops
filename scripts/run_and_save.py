#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Run signal engine pipeline and save decision data for dashboard.

Realtime mode (--realtime):
- Overwrites decision_latest.json every interval (30-60s)
- Does NOT write timestamped snapshots during market hours
- Writes final decision_YYYY-MM-DD_end.json at market close only

One-time mode (default):
- Writes timestamped decision_*.json and decision_latest.json copy
- Enforces retention policy
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
from app.data.theta_v3_pipeline import (
    check_theta_health,
    ThetaHealthStatus,
)

# Data source constants
DATA_SOURCE_LIVE = "live"
DATA_SOURCE_SNAPSHOT = "snapshot"
DATA_SOURCE_UNAVAILABLE = "unavailable"
from app.execution.dry_run_executor import execute_dry_run
from app.execution.execution_gate import evaluate_execution_gate, ExecutionGateResult
from app.execution.execution_plan import build_execution_plan
from app.signals.engine import run_signal_engine
from app.signals.models import CCConfig, CSPConfig, SignalEngineConfig
from app.signals.scoring import ScoringConfig
from app.signals.selection import SelectionConfig


def enforce_daily_retention(output_dir: Path, max_days: int = 7) -> Tuple[int, List[str]]:
    """Keep only decision_latest.json and last N end-of-day snapshots."""
    deleted: List[str] = []
    
    # Files to always keep
    keep_files = {"decision_latest.json", "sample_decision.json", "sample_decision_rich.json"}
    
    # Find all decision files
    decision_files = sorted(
        [f for f in output_dir.glob("decision_*.json") if f.name not in keep_files],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    
    if not decision_files:
        return 0, []
    
    # Keep only _end.json files (end-of-day snapshots) within retention period
    cutoff_date = (date.today() - timedelta(days=max_days)).strftime("%Y-%m-%d")
    
    files_to_delete: List[Path] = []
    kept_end_files = 0
    
    for f in decision_files:
        is_end_file = "_end.json" in f.name
        
        try:
            file_date = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
        except OSError:
            file_date = "1970-01-01"
        
        if is_end_file and file_date >= cutoff_date:
            # Keep end-of-day files within retention period
            kept_end_files += 1
            continue
        
        # Delete non-end files and old end files
        files_to_delete.append(f)
    
    for f in files_to_delete:
        try:
            f.unlink()
            deleted.append(f.name)
        except Exception as e:
            print(f"  Warning: Failed to delete {f.name}: {e}", file=sys.stderr)
    
    return len(deleted), deleted


def _run_health_check(test_mode: bool = False) -> Tuple[bool, str, Optional[str]]:
    """Run Theta Terminal health check."""
    status = check_theta_health()
    
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
) -> Tuple[int, Optional[Dict[str, Any]]]:
    """Run a single pipeline iteration.
    
    Returns (exit_code, output_data).
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
    
    # Configuration - use lower DTE window to ensure data exists
    scoring_config = ScoringConfig(
        premium_weight=1.0, dte_weight=1.0, spread_weight=1.0,
        otm_weight=1.0, liquidity_weight=1.0,
    )
    
    selection_config = SelectionConfig(
        max_total=10, max_per_symbol=2, max_per_signal_type=None, min_score=0.0,
    )
    
    # Lower DTE window: 7-45 days to catch more expirations
    base_config = SignalEngineConfig(
        dte_min=7, dte_max=45, min_bid=0.01, min_open_interest=50,
        max_spread_pct=25.0, scoring_config=scoring_config, selection_config=selection_config,
    )
    
    csp_config = CSPConfig(otm_pct_min=0.03, otm_pct_max=0.20)
    cc_config = CCConfig(otm_pct_min=0.02, otm_pct_max=0.15)
    
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
            print(f"  Options: {options_health.valid_symbols_count} with chains, {options_health.excluded_count} without")
        else:
            print(f"  Options: BLOCKED (0 symbols with options)")
    
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
            "symbols_with_options": len(symbols_with_options),
            "symbols_without_options": len(symbols_without_options),
        },
    }
    
    # Log summary
    if not realtime_mode:
        print(f"\nPipeline complete:")
        print(f"  Data source: {data_source}")
        print(f"  Symbols with options: {len(symbols_with_options)}")
        print(f"  Candidates: {result.stats['total_candidates']}")
        print(f"  Selected: {len(result.selected_signals) if result.selected_signals else 0}")
        print(f"  Gate: {'ALLOWED' if gate_result.allowed else 'BLOCKED'}")
    else:
        ts = datetime.now().strftime("%H:%M:%S")
        candidates = result.stats['total_candidates']
        selected = len(result.selected_signals) if result.selected_signals else 0
        with_opts = len(symbols_with_options)
        print(f"[{ts}] Options:{with_opts} Candidates:{candidates} Selected:{selected} Gate:{'✓' if gate_result.allowed else '✗'}")
    
    return 0, output_data


def write_decision_file(output_data: Dict[str, Any], output_dir: Path, filename: str) -> Optional[Path]:
    """Write decision data to file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    
    try:
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        return output_path
    except Exception as e:
        print(f"  Error writing {filename}: {e}", file=sys.stderr)
        return None


def run_realtime_loop(args: argparse.Namespace, config: Any) -> int:
    """Run pipeline in realtime mode.
    
    - Overwrites decision_latest.json every interval
    - Does NOT write timestamped snapshots during market hours
    - Writes final end-of-day snapshot at market close
    """
    refresh_interval = args.interval if args.interval else get_realtime_refresh_interval()
    end_time_str = get_realtime_end_time()
    output_dir = Path(args.output_dir or config.snapshots.output_dir)
    
    print("=" * 60)
    print("ChakraOps Decision Pipeline - REALTIME MODE")
    print("=" * 60)
    print(f"  Refresh interval: {refresh_interval}s")
    print(f"  End time: {end_time_str}")
    print(f"  Output: {output_dir / 'decision_latest.json'}")
    print(f"  Press Ctrl+C to stop")
    print("=" * 60)
    
    iteration = 0
    last_output_data: Optional[Dict[str, Any]] = None
    
    try:
        while True:
            iteration += 1
            
            # Check end time
            now = datetime.now()
            try:
                end_h, end_m, end_s = map(int, end_time_str.split(":"))
                end_time = now.replace(hour=end_h, minute=end_m, second=end_s, microsecond=0)
                if now >= end_time:
                    print(f"\n[{now.strftime('%H:%M:%S')}] Market close reached")
                    break
            except ValueError:
                pass  # Invalid end_time format, continue indefinitely
            
            # Run pipeline
            exit_code, output_data = run_pipeline(args, config, test_mode=False, realtime_mode=True)
            
            if exit_code != 0:
                print(f"  Pipeline iteration {iteration} failed")
            elif output_data:
                # Write ONLY decision_latest.json (no timestamped file in realtime mode)
                write_decision_file(output_data, output_dir, "decision_latest.json")
                last_output_data = output_data
            
            # Sleep until next iteration
            time.sleep(refresh_interval)
    
    except KeyboardInterrupt:
        print("\n\nRealtime mode interrupted by user")
    
    # Write final end-of-day snapshot
    if last_output_data:
        final_name = f"decision_{date.today().isoformat()}_end.json"
        final_path = write_decision_file(last_output_data, output_dir, final_name)
        if final_path:
            print(f"Final snapshot: {final_path}")
        
        # Cleanup old files
        deleted, _ = enforce_daily_retention(output_dir, max_days=get_snapshot_retention_days())
        if deleted > 0:
            print(f"Cleanup: Deleted {deleted} old file(s)")
    
    print("Realtime mode ended")
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run decision pipeline and save to JSON"
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit symbols")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    parser.add_argument("--test", action="store_true", help="Test mode with diagnostics")
    parser.add_argument("--no-fallback", action="store_true", help="Disable fallback")
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip cleanup")
    parser.add_argument("--realtime", action="store_true", help="Realtime mode: update every interval")
    parser.add_argument("--interval", type=int, default=30, help="Refresh interval (seconds, default: 30)")
    args = parser.parse_args()
    
    config = load_config()
    
    if args.realtime:
        return run_realtime_loop(args, config)
    
    # One-time mode
    if args.test:
        print("=" * 60)
        print("ChakraOps Decision Pipeline - TEST MODE")
        print("=" * 60)
    
    print("Checking Theta Terminal connectivity...")
    
    exit_code, output_data = run_pipeline(args, config, test_mode=args.test)
    
    if exit_code != 0:
        return exit_code
    
    if not output_data:
        return 1
    
    # Save files
    output_dir = Path(args.output_dir or config.snapshots.output_dir)
    
    # Write timestamped file
    iso_ts = output_data["decision_snapshot"].get("as_of") or "unknown"
    safe_iso_ts = str(iso_ts).replace(":", "-")
    timestamped_file = write_decision_file(output_data, output_dir, f"decision_{safe_iso_ts}.json")
    
    # Write latest file
    latest_file = write_decision_file(output_data, output_dir, "decision_latest.json")
    
    if timestamped_file:
        print(f"  Output: {timestamped_file}")
    if latest_file:
        print(f"  Latest: {latest_file}")
    
    # Cleanup
    if not args.skip_cleanup:
        deleted, _ = enforce_daily_retention(output_dir, max_days=get_snapshot_retention_days())
        if deleted > 0:
            print(f"  Cleanup: Deleted {deleted} old file(s)")
    
    # Slack notification (only on gate state change)
    slack_state_path = output_dir / ".slack_state.json"
    gate_result = output_data.get("execution_gate", {})
    
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
            snapshot=output_data.get("decision_snapshot", {}),
            gate_result=gate_result,
            execution_plan=output_data.get("execution_plan", {}),
            decision_file_path=timestamped_file,
            last_gate_allowed=last_gate_allowed,
        )
        
        try:
            with open(slack_state_path, "w") as f:
                json.dump({"last_gate_allowed": gate_result.get("allowed")}, f)
        except OSError:
            pass
        
        if sent:
            print("  Slack alert sent")
    except Exception as e:
        print(f"  Slack: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
