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

# Load .env so ORATS_API_TOKEN and other vars are available
from dotenv import load_dotenv
load_dotenv(repo_root / ".env")

from app.core.settings import (
    get_confidence_config,
    get_environment_config,
    get_min_stock_price,
    get_options_context_config,
    get_output_dir,
    get_portfolio_config,
    get_run_mode,
    get_snapshot_max_files,
    get_snapshot_retention_days,
    get_realtime_refresh_interval,
    get_realtime_end_time,
    is_fallback_enabled,
    load_config,
)
from app.core.freeze_guard import (
    build_critical_config_snapshot,
    check_freeze,
    record_run,
)
from app.core.environment.data_completeness_guard import check_data_completeness
from app.core.environment.earnings_gate import check_earnings_gate
from app.core.environment.event_calendar import DefaultEventCalendar
from app.core.environment.macro_event_gate import check_macro_event_gate
from app.core.environment.session_gate import check_session_gate
from app.core.observability.rejection_analytics import summarize_rejections
from app.core.observability.trust_reports import generate_daily_report
from app.core.observability.why_no_trade import explain_no_trade
from app.core.persistence import (
    get_enabled_symbols,
    list_open_positions,
    save_decision_artifact_metadata,
)
from app.core.execution_guard import check_portfolio_caps
from app.core.market.stock_universe import StockUniverseManager
from app.core.options.options_availability import (
    DiagnosticsOptionsChainProvider,
    OptionsAvailabilityRecorder,
)
from app.core.gates.options_data_health import evaluate_options_data_health
from app.data.options_chain_provider import (
    FallbackWeeklyExpirationsProvider,
    OratsOptionsChainProvider,
)
from app.data.stock_snapshot_provider import StockSnapshotProvider

# Data source constants
DATA_SOURCE_LIVE = "live"
DATA_SOURCE_SNAPSHOT = "snapshot"
DATA_SOURCE_UNAVAILABLE = "unavailable"
from app.core.engine.regime_gate import evaluate_regime_gate
from app.execution.dry_run_executor import execute_dry_run
from app.execution.execution_gate import evaluate_execution_gate, ExecutionGateResult
from app.execution.execution_plan import build_execution_plan
from app.signals.engine import run_signal_engine
from app.signals.models import CCConfig, CSPConfig, SignalEngineConfig
from app.signals.scoring import ScoringConfig
from app.signals.context_gating import ContextGateConfig
from app.signals.selection import SelectionConfig
from app.core.trade_construction import build_trade, build_iron_condor_trade
from app.models.trade_proposal import TradeProposal, set_execution_readiness
from app.core.persistence import (
    get_daily_run_cycle,
    save_daily_rejection_summary,
    save_trade_proposal,
    save_trust_report,
    set_daily_run_cycle_complete,
    start_daily_run_cycle,
    update_daily_run_cycle_phase,
)


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
    """Run ORATS Live Data health check."""
    from app.core.options.providers.orats_provider import OratsOptionsChainProvider
    provider = OratsOptionsChainProvider()
    status = provider.healthcheck()
    ok = status.get("ok", False)
    msg = status.get("message", "Unknown")
    if test_mode:
        print(f"  Health check: {msg}")
        if status.get("response_time_ms") is not None:
            print(f"  Response time: {status['response_time_ms']:.1f}ms")
    if ok:
        return True, msg, None
    if is_fallback_enabled():
        return False, msg, DATA_SOURCE_SNAPSHOT
    return False, msg, None


def run_pipeline(
    args: argparse.Namespace,
    config: Any,
    test_mode: bool = False,
    realtime_mode: bool = False,
) -> Tuple[int, Optional[Dict[str, Any]]]:
    """Run a single pipeline iteration.
    
    Returns (exit_code, output_data).
    """
    run_mode = get_run_mode()
    critical_snapshot = build_critical_config_snapshot()
    freeze_result = check_freeze(run_mode)
    if not freeze_result.allowed:
        print(f"ERROR: {freeze_result.message}", file=sys.stderr)
        if freeze_result.changed_keys:
            print(f"  Changed keys: {', '.join(freeze_result.changed_keys)}", file=sys.stderr)
        return 1, None

    # Phase 6.2: deterministic daily cycle — block duplicate run unless force_run
    cycle_id = date.today().isoformat()
    force_run = getattr(args, "force_run", False)
    existing_cycle = get_daily_run_cycle(cycle_id)
    if existing_cycle and existing_cycle.get("phase") == "COMPLETE" and not force_run:
        if not realtime_mode:
            print(f"Daily cycle {cycle_id} already COMPLETE. No re-run. Use --force-run to override.", file=sys.stderr)
        return 0, None
    if not existing_cycle:
        start_daily_run_cycle(cycle_id)
    try:
        update_daily_run_cycle_phase(cycle_id, "SNAPSHOT")
    except Exception:
        pass

    # Phase 10: market heartbeat — update last_market_check on every run attempt
    try:
        from app.api.market_status import update_heartbeat
        update_heartbeat()
    except Exception:
        pass

    output_dir_str = args.output_dir or config.snapshots.output_dir
    
    if test_mode:
        print("-" * 60)
        print("  Options data: ORATS Live (ORATS_API_TOKEN)")
        print(f"  Fallback enabled: {config.theta.fallback_enabled and not args.no_fallback}")
        print(f"  Output dir: {output_dir_str}")
        print("-" * 60)
    
    # Health check (ORATS)
    healthy, health_msg, fallback_data_source = _run_health_check(test_mode)
    data_source = DATA_SOURCE_LIVE
    
    if not healthy:
        print(f"  ORATS: {health_msg}")
        if args.no_fallback or not is_fallback_enabled():
            print("ERROR: ORATS not available and fallback disabled. Set ORATS_API_TOKEN.")
            return 1, None
        print("  Fallback: Using latest snapshot")
        data_source = DATA_SOURCE_SNAPSHOT
    else:
        if not realtime_mode:
            print("  ORATS: OK")
    
    # Initialize providers
    snapshot_provider = StockSnapshotProvider()
    options_provider_inner = OratsOptionsChainProvider()
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
    
    min_price = get_min_stock_price()
    universe_manager = StockUniverseManager(
        snapshot_provider, symbols_from_db=enabled_symbols, min_price=min_price
    )
    eligible_stocks = universe_manager.get_eligible_stocks()
    
    if args.limit:
        eligible_stocks = eligible_stocks[:args.limit]
    
    if not realtime_mode:
        print(f"Processing {len(eligible_stocks)} symbols...")
    
    opts_ctx = get_options_context_config()
    # Configuration - credit 50%, DTE 25%, liquidity 25%; Phase 3.2/3.3 context and strategy preference
    scoring_config = ScoringConfig(
        premium_weight=0.50,
        dte_weight=0.25,
        liquidity_weight=0.25,
        spread_weight=0.0,
        otm_weight=0.0,
        context_weight=0.0,
        strategy_preference_weight=opts_ctx.get("strategy_preference_weight", 0.15),
        strategy_iv_rank_high_pct=opts_ctx.get("strategy_iv_rank_high_pct", 60.0),
        strategy_iv_rank_low_pct=opts_ctx.get("strategy_iv_rank_low_pct", 20.0),
        strategy_term_slope_backwardation_min=opts_ctx.get("strategy_term_slope_backwardation_min", 0.0),
        strategy_term_slope_contango_max=opts_ctx.get("strategy_term_slope_contango_max", 0.0),
    )
    context_gate = ContextGateConfig(
        iv_rank_min_sell_pct=opts_ctx.get("iv_rank_min_sell_pct", 10.0),
        iv_rank_max_sell_pct=opts_ctx.get("iv_rank_max_sell_pct", 90.0),
        iv_rank_max_buy_pct=opts_ctx.get("iv_rank_max_buy_pct", 70.0),
        dte_event_window=opts_ctx.get("dte_event_window", 7),
        expected_move_gate=opts_ctx.get("expected_move_gate", True),
    )
    selection_config = SelectionConfig(
        max_total=10,
        max_per_symbol=2,
        max_per_signal_type=None,
        min_score=0.0,
        min_confidence_threshold=get_confidence_config().get("min_confidence_threshold", 40),
        context_gate=context_gate,
    )
    
    # Lower DTE window: 7-45 days to catch more expirations
    base_config = SignalEngineConfig(
        dte_min=7, dte_max=45, min_bid=0.01, min_open_interest=50,
        max_spread_pct=25.0, scoring_config=scoring_config, selection_config=selection_config,
    )
    
    csp_config = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)
    cc_config = CCConfig(delta_min=0.15, delta_max=0.35, prob_otm_min=0.70)
    
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

    try:
        update_daily_run_cycle_phase(cycle_id, "DECISION")
    except Exception:
        pass

    # Options health gate
    symbols_with_options = list(decision_snapshot.symbols_with_options or [])
    symbols_without_options = dict(decision_snapshot.symbols_without_options or {})
    options_health = evaluate_options_data_health(symbols_with_options, symbols_without_options)
    
    if not realtime_mode:
        if options_health.allowed:
            print(f"  Options: {options_health.valid_symbols_count} with chains, {options_health.excluded_count} without")
        else:
            print(f"  Options: BLOCKED (0 symbols with options)")
    
    # Risk posture (Phase 4.5.5): scaffold only; no threshold changes yet.
    # Future extension: use risk_posture to relax min_trading_days_to_expiry, earnings_block_window_days, etc.
    env_config = get_environment_config()
    risk_posture = env_config.get("risk_posture")
    if risk_posture is not None and hasattr(risk_posture, "value"):
        risk_posture_str = risk_posture.value
    else:
        risk_posture_str = str(risk_posture) if risk_posture is not None else "CONSERVATIVE"

    # Execution gate
    gate_result = evaluate_execution_gate(decision_snapshot)

    portfolio_config = get_portfolio_config()
    # Portfolio caps (Phase 2.5): block new trades when caps exceeded
    if gate_result.allowed and decision_snapshot.selected_signals and len(decision_snapshot.selected_signals) > 0:
        open_positions = list_open_positions()
        account_balance = portfolio_config.get("account_balance", 100_000.0)
        first_selected = decision_snapshot.selected_signals[0]
        scored_dict = first_selected.get("scored", {}) if isinstance(first_selected, dict) else {}
        candidate_dict = scored_dict.get("candidate", {}) if isinstance(scored_dict, dict) else {}
        symbol = candidate_dict.get("symbol")
        strike = candidate_dict.get("strike")
        contracts = 1
        mid_price = candidate_dict.get("mid")
        bid_price = candidate_dict.get("bid")
        premium = candidate_dict.get("premium_collected")
        if premium is None and (mid_price is not None or bid_price is not None):
            premium = (mid_price if mid_price is not None else bid_price) * contracts * 100
        candidate = {
            "symbol": symbol,
            "strike": strike,
            "contracts": contracts,
            "premium_collected": premium,
            "mid": mid_price,
            "bid": bid_price,
            "delta": candidate_dict.get("delta"),
        }
        portfolio_reasons = check_portfolio_caps(
            open_positions, candidate, account_balance, portfolio_config
        )
        if portfolio_reasons:
            gate_result = ExecutionGateResult(
                allowed=False,
                reasons=list(gate_result.reasons or []) + portfolio_reasons,
            )

    if not options_health.allowed:
        combined_reasons = list(gate_result.reasons or []) + options_health.reasons
        gate_result = ExecutionGateResult(allowed=False, reasons=combined_reasons)

    # Earnings gate (Phase 4.5.1): block when within earnings window or event_flags contains earnings
    # Future extension: risk_posture may shorten earnings_block_window_days for BALANCED/AGGRESSIVE
    if gate_result.allowed and result.selected_signals and len(result.selected_signals) > 0:
        first_selected = result.selected_signals[0]
        option_ctx = first_selected.scored.candidate.option_context
        env_config = get_environment_config()
        earnings_reason = check_earnings_gate(option_ctx, env_config)
        if earnings_reason is not None:
            gate_result = ExecutionGateResult(
                allowed=False,
                reasons=list(gate_result.reasons or []) + ["EARNINGS_WINDOW"],
            )

    # Macro event gate (Phase 4.5.2): block when FOMC/CPI/JOBS/NFP/FED within window
    if gate_result.allowed:
        env_config = get_environment_config()
        event_calendar = DefaultEventCalendar()
        macro_reason = check_macro_event_gate(event_calendar, env_config)
        if macro_reason is not None:
            gate_result = ExecutionGateResult(
                allowed=False,
                reasons=list(gate_result.reasons or []) + ["MACRO_EVENT_WINDOW"],
            )

    # Session gate (Phase 4.5.3): block on short sessions and insufficient trading days to expiry
    # Future extension: risk_posture may reduce min_trading_days_to_expiry for BALANCED/AGGRESSIVE
    if gate_result.allowed:
        env_config = get_environment_config()
        today_d = date.today()
        expiry_d = None
        if result.selected_signals and len(result.selected_signals) > 0:
            expiry_d = getattr(
                result.selected_signals[0].scored.candidate,
                "expiry",
                None,
            )
        session_reasons = check_session_gate(today_d, expiry_d, env_config)
        if session_reasons:
            gate_result = ExecutionGateResult(
                allowed=False,
                reasons=list(gate_result.reasons or []) + session_reasons,
            )

    # Data completeness guard (Phase 4.5.4): block when required data missing (before trade construction)
    if gate_result.allowed and result.selected_signals and len(result.selected_signals) > 0:
        first_selected = result.selected_signals[0]
        option_ctx = first_selected.scored.candidate.option_context
        data_reason = check_data_completeness(first_selected, option_ctx)
        if data_reason is not None:
            gate_result = ExecutionGateResult(
                allowed=False,
                reasons=list(gate_result.reasons or []) + ["DATA_INCOMPLETE"],
            )

    # Regime (volatility kill switch): RISK_OFF blocks execution readiness (Phase 4.4)
    regime, regime_reason = evaluate_regime_gate(None)

    # Phase 4.1: Trade construction (deterministic; no execution). Attach TradeProposal to decision.
    trade_proposal: Optional[TradeProposal] = None
    if result.selected_signals and len(result.selected_signals) > 0:
        first_selected = result.selected_signals[0]
        option_ctx = first_selected.scored.candidate.option_context
        trade_proposal = build_trade(first_selected, option_ctx, portfolio_config)
        # Phase 4.3/4.4: READY only when not rejected, gate allowed, AND regime=RISK_ON (kill switch blocks)
        gate_and_regime_ok = gate_result.allowed and regime == "RISK_ON"
        trade_proposal = set_execution_readiness(trade_proposal, gate_and_regime_ok)

    try:
        update_daily_run_cycle_phase(cycle_id, "TRADE_PROPOSAL")
    except Exception:
        pass

    execution_plan = build_execution_plan(decision_snapshot, gate_result)
    dry_run_result = execute_dry_run(execution_plan)
    
    # Prepare output
    pipeline_timestamp = datetime.now(timezone.utc).isoformat()
    decision_snapshot_dict = asdict(decision_snapshot)
    decision_snapshot_dict["data_source"] = data_source
    decision_snapshot_dict["pipeline_timestamp"] = pipeline_timestamp
    if trade_proposal is not None:
        proposal_dict = trade_proposal.to_dict()
        decision_snapshot_dict["trade_proposal"] = proposal_dict
        # Phase 4.3: persist trade proposal to DB (track acknowledged vs skipped)
        try:
            save_trade_proposal(
                decision_ts=pipeline_timestamp,
                proposal_json=proposal_dict,
                execution_status=proposal_dict.get("execution_status", "BLOCKED"),
            )
        except Exception as e:
            if not realtime_mode:
                print(f"  Warning: failed to persist trade proposal: {e}", file=sys.stderr)
    else:
        decision_snapshot_dict["trade_proposal"] = None

    # Phase 5.1: Why-no-trade explanation when no READY trades
    why_result = explain_no_trade(decision_snapshot, gate_result, trade_proposal)
    if why_result.get("no_trade"):
        decision_snapshot_dict["why_no_trade"] = why_result

    # Phase 5.2: Rejection analytics — store daily summary in DB
    rejection_summary = summarize_rejections(decision_snapshot, gate_result)
    rejection_summary["as_of"] = pipeline_timestamp
    try:
        save_daily_rejection_summary(date.today().isoformat(), rejection_summary)
    except Exception as e:
        if not realtime_mode:
            print(f"  Warning: failed to save daily rejection summary: {e}", file=sys.stderr)

    # Phase 5.3: Daily trust report — save to DB and optional JSON
    run_mode_str = run_mode.value if hasattr(run_mode, "value") else str(run_mode)
    from app.core.persistence import get_capital_deployed_today, get_mtd_realized_pnl
    daily_report = generate_daily_report(
        decision_snapshot, gate_result, trade_proposal, as_of=pipeline_timestamp,
        run_mode=run_mode_str,
        config_frozen=freeze_result.config_frozen,
        freeze_violation_changed_keys=freeze_result.changed_keys if not freeze_result.allowed else None,
        capital_deployed_today=get_capital_deployed_today(),
        month_to_date_realized_pnl=get_mtd_realized_pnl(),
    )
    daily_report["date"] = date.today().isoformat()
    daily_report["run_mode"] = run_mode_str
    daily_report["config_frozen"] = freeze_result.config_frozen
    if freeze_result.changed_keys:
        daily_report["freeze_violation_changed_keys"] = freeze_result.changed_keys
    try:
        save_trust_report("daily", date.today().isoformat(), daily_report)
    except Exception as e:
        if not realtime_mode:
            print(f"  Warning: failed to save daily trust report: {e}", file=sys.stderr)

    try:
        update_daily_run_cycle_phase(cycle_id, "OBSERVABILITY")
    except Exception:
        pass

    # Phase 6.2: cycle_id and phase timing in metadata and trust report
    cycle_row = get_daily_run_cycle(cycle_id)
    cycle_started_at = cycle_row.get("started_at") if cycle_row else None
    daily_report["cycle_id"] = cycle_id
    daily_report["cycle_phase"] = "OBSERVABILITY"
    daily_report["cycle_started_at"] = cycle_started_at

    output_data = {
        "decision_snapshot": decision_snapshot_dict,
        "execution_gate": asdict(gate_result),
        "execution_plan": asdict(execution_plan),
        "dry_run_result": asdict(dry_run_result),
        "regime": regime,
        "regime_reason": regime_reason,
        "daily_trust_report": daily_report,
        "metadata": {
            "data_source": data_source,
            "pipeline_timestamp": decision_snapshot_dict["pipeline_timestamp"],
            "options_provider": "orats",
            "fallback_enabled": config.theta.fallback_enabled,
            "symbols_with_options": len(symbols_with_options),
            "symbols_without_options": len(symbols_without_options),
            "risk_posture": risk_posture_str,
            "run_mode": run_mode_str,
            "config_frozen": freeze_result.config_frozen,
            "cycle_id": cycle_id,
            "cycle_phase": "OBSERVABILITY",
            "cycle_started_at": cycle_started_at,
        },
    }

    # Phase 6.2: mark daily cycle COMPLETE only in one-time mode (realtime sets COMPLETE at end of loop)
    if not realtime_mode:
        try:
            set_daily_run_cycle_complete(cycle_id)
        except Exception as e:
            print(f"  Warning: failed to set cycle COMPLETE: {e}", file=sys.stderr)
        output_data["metadata"]["cycle_phase"] = "COMPLETE"
        daily_report["cycle_phase"] = "COMPLETE"

    # Phase 6.1: record config for next freeze check
    try:
        record_run(critical_snapshot, run_mode)
    except Exception as e:
        if not realtime_mode:
            print(f"  Warning: failed to record config freeze state: {e}", file=sys.stderr)

    # Phase 6.5: store decision artifact meta for UI read models
    try:
        meta = {
            "decision_ts": pipeline_timestamp,
            "regime": regime,
            "regime_reason": regime_reason,
            "stats": decision_snapshot_dict.get("stats"),
            "why_no_trade": decision_snapshot_dict.get("why_no_trade"),
            "metadata": output_data.get("metadata"),
        }
        save_decision_artifact_metadata(pipeline_timestamp, json.dumps(meta))
    except Exception as e:
        if not realtime_mode:
            print(f"  Warning: failed to save decision artifact meta: {e}", file=sys.stderr)
    
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
    # Phase 6.2: block if today's cycle already COMPLETE (unless force_run)
    cycle_id = date.today().isoformat()
    force_run = getattr(args, "force_run", False)
    existing_cycle = get_daily_run_cycle(cycle_id)
    if existing_cycle and existing_cycle.get("phase") == "COMPLETE" and not force_run:
        print(f"Daily cycle {cycle_id} already COMPLETE. No re-run. Use --force-run to override.", file=sys.stderr)
        return 0

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
        
        # Phase 6.2: mark daily cycle COMPLETE at end of realtime day
        try:
            set_daily_run_cycle_complete(cycle_id)
        except Exception as e:
            print(f"  Warning: failed to set cycle COMPLETE: {e}", file=sys.stderr)
        
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
    parser.add_argument("--force-run", action="store_true", help="Override: allow run even if daily cycle already COMPLETE (Phase 6.2)")
    args = parser.parse_args()
    
    config = load_config()
    
    if args.realtime:
        return run_realtime_loop(args, config)
    
    # One-time mode
    if args.test:
        print("=" * 60)
        print("ChakraOps Decision Pipeline - TEST MODE")
        print("=" * 60)
    
    print("Checking ORATS connectivity...")
    
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

    # Phase 10: persist evaluation_emitted and last_evaluated_at for /api/market-status
    try:
        from app.api.market_status import write_market_status
        pipeline_ts = output_data.get("decision_snapshot", {}).get("as_of") or output_data.get("metadata", {}).get("pipeline_timestamp")
        if pipeline_ts:
            write_market_status(
                last_evaluated_at=str(pipeline_ts),
                evaluation_attempted=True,
                evaluation_emitted=True,
                skip_reason=None,
                source_mode=output_data.get("metadata", {}).get("run_mode", "DRY_RUN"),
            )
    except Exception:
        pass

    # Phase 5.3: save daily trust report to JSON
    daily_report = output_data.get("daily_trust_report")
    if daily_report:
        report_date = daily_report.get("date") or date.today().isoformat()
        trust_report_path = output_dir / f"trust_report_daily_{report_date}.json"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(trust_report_path, "w") as f:
                json.dump(daily_report, f, indent=2)
        except OSError as e:
            print(f"  Warning: failed to write trust report JSON: {e}", file=sys.stderr)
    
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
    gate_result_dict = output_data.get("execution_gate", {})
    plan_dict = output_data.get("execution_plan", {})
    snapshot_dict = output_data.get("decision_snapshot", {})
    
    last_gate_allowed = None
    if slack_state_path.exists():
        try:
            with open(slack_state_path) as f:
                state = json.load(f)
            last_gate_allowed = state.get("last_gate_allowed")
        except (json.JSONDecodeError, OSError):
            pass
    
    try:
        from types import SimpleNamespace
        from app.execution.execution_gate import ExecutionGateResult
        from app.execution.execution_plan import ExecutionPlan, ExecutionOrder
        from app.notifications.slack_notifier import send_decision_alert

        gate_result = ExecutionGateResult(
            allowed=bool(gate_result_dict.get("allowed", False)),
            reasons=list(gate_result_dict.get("reasons") or []),
        )
        orders = []
        for o in plan_dict.get("orders") or []:
            orders.append(ExecutionOrder(
                symbol=o.get("symbol", ""),
                action=o.get("action", "SELL_TO_OPEN"),
                strike=float(o.get("strike", 0)),
                expiry=o.get("expiry", ""),
                option_right=o.get("option_right", "PUT"),
                quantity=int(o.get("quantity", 1)),
                limit_price=float(o.get("limit_price", 0)),
            ))
        execution_plan = ExecutionPlan(
            allowed=bool(plan_dict.get("allowed", False)),
            blocked_reason=plan_dict.get("blocked_reason"),
            orders=orders,
        )
        snapshot = SimpleNamespace(**snapshot_dict) if snapshot_dict else SimpleNamespace()

        sent = send_decision_alert(
            snapshot=snapshot,
            gate_result=gate_result,
            execution_plan=execution_plan,
            decision_file_path=timestamped_file,
            last_gate_allowed=last_gate_allowed,
        )

        try:
            with open(slack_state_path, "w") as f:
                json.dump({"last_gate_allowed": gate_result.allowed}, f)
        except OSError:
            pass

        if sent:
            print("  Slack alert sent")
    except Exception as e:
        print(f"  Slack: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
