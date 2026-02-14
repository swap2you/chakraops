# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Nightly Evaluation Runner.

Runs a full universe evaluation (typically after market close) and sends
a summary to Slack. Can be triggered via CLI or scheduler.

Usage:
    python -m chakraops.run_evaluation --mode nightly --asof last_close
    python -m chakraops.run_evaluation --mode nightly --dry-run

Configuration (env vars):
    NIGHTLY_EVAL_TIME       - Time to run (HH:MM, 24h format, default: 19:00)
    NIGHTLY_EVAL_TZ         - Timezone (default: America/New_York)
    NIGHTLY_MAX_SYMBOLS     - Max symbols to evaluate (default: all)
    NIGHTLY_STAGE2_TOP_K    - Top K for stage 2 (default: 20)
    SLACK_WEBHOOK_URL       - Slack webhook for notifications
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class NightlyConfig:
    """Configuration for nightly evaluation."""
    eval_time: str = "19:00"  # HH:MM in 24h format
    timezone: str = "America/New_York"
    max_symbols: Optional[int] = None  # None = all
    stage2_top_k: int = 20
    slack_webhook_url: Optional[str] = None
    dry_run: bool = False
    
    @classmethod
    def from_env(cls) -> "NightlyConfig":
        """Load configuration from environment variables."""
        return cls(
            eval_time=os.getenv("NIGHTLY_EVAL_TIME", "19:00"),
            timezone=os.getenv("NIGHTLY_EVAL_TZ", "America/New_York"),
            max_symbols=int(os.getenv("NIGHTLY_MAX_SYMBOLS")) if os.getenv("NIGHTLY_MAX_SYMBOLS") else None,
            stage2_top_k=int(os.getenv("NIGHTLY_STAGE2_TOP_K", "20")),
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
        )


# ============================================================================
# Slack Summary Builder
# ============================================================================

@dataclass
class NightlySummary:
    """Summary data for Slack notification."""
    run_id: str
    timestamp: str
    regime: Optional[str] = None
    risk_posture: Optional[str] = None
    duration_seconds: float = 0.0

    # Counts
    universe_total: int = 0
    evaluated: int = 0
    stage1_pass: int = 0
    stage2_pass: int = 0
    eligible: int = 0
    holds: int = 0
    blocks: int = 0
    errors_count: int = 0

    # Phase 8.8/8.9: Eval throughput (optional)
    cache_hit_rate_pct: Optional[float] = None
    requests_estimated: Optional[int] = None
    top_endpoint_hit_rate: Optional[str] = None

    # Phase 9.0: Universe gates
    gate_skips_count: int = 0
    gate_skips_total: int = 0
    gate_skip_reasons_summary: Optional[str] = None

    # Top candidates and holds
    top_eligible: List[Dict[str, Any]] = field(default_factory=list)
    top_holds: List[Dict[str, Any]] = field(default_factory=list)


def build_slack_message(summary: NightlySummary) -> Dict[str, Any]:
    """
    Build Slack message payload from nightly summary.
    
    Format:
    - Header: run_id, timestamp, regime, risk posture
    - Counts: universe, evaluated, stage1_pass, stage2_pass, eligible, holds, blocks
    - Top 5 eligible with symbol/strategy/contract summary
    - Top 5 holds with reasons (DATA_INCOMPLETE etc.)
    """
    # Header section
    header_text = f"*Nightly Evaluation Complete* | `{summary.run_id}`"
    
    # Context line
    regime_str = summary.regime or "UNKNOWN"
    risk_str = summary.risk_posture or "UNKNOWN"
    duration_str = f"{summary.duration_seconds:.1f}s" if summary.duration_seconds else "N/A"
    context_text = f"_{summary.timestamp}_ | Regime: *{regime_str}* | Risk: *{risk_str}* | Duration: {duration_str}"
    
    # Counts section
    counts_lines = [
        f"*Universe:* {summary.universe_total} symbols",
        f"*Evaluated:* {summary.evaluated}",
        f"*Stage 1 Pass:* {summary.stage1_pass}",
        f"*Stage 2 (Chain):* {summary.stage2_pass}",
        f"*Eligible:* {summary.eligible} :white_check_mark:",
        f"*Holds:* {summary.holds} :hourglass_flowing_sand:",
        f"*Blocks:* {summary.blocks} :no_entry:",
    ]
    if summary.errors_count > 0:
        counts_lines.append(f"*Errors:* {summary.errors_count} :warning:")
    # Phase 8.8/8.9: Eval throughput line
    if summary.cache_hit_rate_pct is not None or summary.requests_estimated is not None:
        parts = [
            f"processed {summary.evaluated} symbols",
            f"wall time {summary.duration_seconds:.0f}s",
        ]
        if summary.cache_hit_rate_pct is not None:
            parts.append(f"cache hit rate {summary.cache_hit_rate_pct:.0f}%")
        if summary.requests_estimated is not None:
            parts.append(f"requests_est {summary.requests_estimated}")
        if summary.top_endpoint_hit_rate:
            parts.append(summary.top_endpoint_hit_rate)
        counts_lines.append(f"*Eval throughput:* {', '.join(parts)}")
    # Phase 9.0: Universe gates summary
    if summary.gate_skips_count > 0 and summary.gate_skips_total > 0:
        gate_line = f"*Universe Gates:* skipped {summary.gate_skips_count}/{summary.gate_skips_total}"
        if summary.gate_skip_reasons_summary:
            gate_line += f" ({summary.gate_skip_reasons_summary})"
        counts_lines.append(gate_line)
    counts_text = "\n".join(counts_lines)

    # Top eligible section
    eligible_section = ""
    if summary.top_eligible:
        eligible_lines = ["*Top Eligible Candidates:*"]
        for i, cand in enumerate(summary.top_eligible[:5], 1):
            symbol = cand.get("symbol", "???")
            score = cand.get("score", 0)
            
            # Contract info if available
            contract = cand.get("selected_contract")
            if contract and isinstance(contract, dict):
                c_data = contract.get("contract", {})
                strike = c_data.get("strike", "?")
                exp = c_data.get("expiration", "?")
                delta = c_data.get("delta")
                delta_str = f"d{delta:.2f}" if delta is not None else ""
                bid = c_data.get("bid")
                bid_str = f"${bid:.2f}" if bid is not None else ""
                eligible_lines.append(
                    f"  {i}. *{symbol}* | Score: {score} | "
                    f"${strike} {exp} {delta_str} {bid_str}"
                )
            else:
                # Legacy format
                trades = cand.get("candidate_trades", [])
                if trades:
                    t = trades[0]
                    strike = t.get("strike", "?")
                    exp = t.get("expiry", "?")
                    delta = t.get("delta")
                    delta_str = f"d{delta:.2f}" if delta is not None else ""
                    eligible_lines.append(
                        f"  {i}. *{symbol}* | Score: {score} | "
                        f"${strike} {exp} {delta_str}"
                    )
                else:
                    eligible_lines.append(f"  {i}. *{symbol}* | Score: {score}")
        eligible_section = "\n".join(eligible_lines)
    else:
        eligible_section = "*No eligible candidates today.*"
    
    # Top holds section
    holds_section = ""
    if summary.top_holds:
        holds_lines = ["*Top Holds (review needed):*"]
        for i, hold in enumerate(summary.top_holds[:5], 1):
            symbol = hold.get("symbol", "???")
            reason = hold.get("primary_reason", "Unknown reason")
            # Truncate long reasons
            if len(reason) > 60:
                reason = reason[:57] + "..."
            holds_lines.append(f"  {i}. *{symbol}* - {reason}")
        holds_section = "\n".join(holds_lines)
    
    # Assemble message blocks
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "ChakraOps Nightly Evaluation", "emoji": True}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": header_text}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": context_text}]
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": counts_text}
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": eligible_section}
        },
    ]
    
    if holds_section:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": holds_section}
        })
    
    return {"blocks": blocks}


def build_slack_message_simple(summary: NightlySummary) -> str:
    """Build simple text Slack message (fallback)."""
    lines = [
        f"*ChakraOps Nightly Evaluation* | `{summary.run_id}`",
        f"_{summary.timestamp}_ | Regime: {summary.regime or 'UNKNOWN'} | Risk: {summary.risk_posture or 'UNKNOWN'}",
        "",
        f"Universe: {summary.universe_total} | Evaluated: {summary.evaluated}",
        f"Stage1: {summary.stage1_pass} | Stage2: {summary.stage2_pass}",
        f"*Eligible: {summary.eligible}* | Holds: {summary.holds} | Blocks: {summary.blocks}",
        "",
    ]
    
    if summary.top_eligible:
        lines.append("*Top Eligible:*")
        for i, cand in enumerate(summary.top_eligible[:5], 1):
            symbol = cand.get("symbol", "???")
            score = cand.get("score", 0)
            reason = cand.get("primary_reason", "")[:40]
            lines.append(f"  {i}. {symbol} (score: {score}) - {reason}")
    else:
        lines.append("_No eligible candidates today._")
    
    if summary.top_holds:
        lines.append("")
        lines.append("*Top Holds:*")
        for i, hold in enumerate(summary.top_holds[:5], 1):
            symbol = hold.get("symbol", "???")
            reason = hold.get("primary_reason", "Unknown")[:40]
            lines.append(f"  {i}. {symbol} - {reason}")
    
    return "\n".join(lines)


# ============================================================================
# Slack Notification
# ============================================================================

def send_nightly_slack(summary: NightlySummary, webhook_url: Optional[str] = None) -> tuple[bool, str]:
    """
    Send nightly summary to Slack.
    
    Returns:
        (success, message)
    """
    import requests
    
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return False, "Slack not configured - SLACK_WEBHOOK_URL not set"
    
    try:
        # Try rich block format first
        payload = build_slack_message(summary)
        resp = requests.post(url, json=payload, timeout=10)
        
        if resp.status_code != 200:
            # Fall back to simple text
            simple_text = build_slack_message_simple(summary)
            resp = requests.post(url, json={"text": simple_text}, timeout=10)
        
        if resp.status_code == 200:
            return True, "Slack notification sent"
        else:
            return False, f"Slack returned {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return False, f"Slack request failed: {e}"


# ============================================================================
# Nightly Evaluation Runner
# ============================================================================

def run_nightly_evaluation(
    config: Optional[NightlyConfig] = None,
    asof: str = "last_close",
) -> Dict[str, Any]:
    """
    Run a full nightly evaluation.
    
    Args:
        config: Configuration (defaults to from_env())
        asof: Reference point ("last_close", "now", or ISO timestamp)
    
    Returns:
        Dict with run_id, success, summary, slack_sent, etc.
    """
    from app.core.eval.evaluation_store import (
        EvaluationRunFull,
        generate_run_id,
        save_run,
        update_latest_pointer,
    )
    
    config = config or NightlyConfig.from_env()
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = generate_run_id()
    
    logger.info("[NIGHTLY] start_eval run_id=%s correlation_id=%s asof=%s", run_id, run_id, asof)
    print(f"[NIGHTLY] Starting evaluation {run_id} (asof={asof})")
    
    result: Dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at,
        "success": False,
        "dry_run": config.dry_run,
    }
    
    if config.dry_run:
        logger.info("[NIGHTLY] Dry run - skipping actual evaluation")
        result["message"] = "Dry run completed"
        result["success"] = True
        return result
    
    start_time = time.time()

    try:
        # Phase 8.8: Reset cache stats at run start
        try:
            from app.core.data.cache_store import reset_cache_stats
            reset_cache_stats()
        except Exception:
            pass

        # Phase 8.9: Prune cache at start (do not fail run)
        try:
            from app.core.data.cache_pruner import prune_cache
            from app.core.config.eval_config import CACHE_DIR, CACHE_MAX_AGE_DAYS, CACHE_MAX_FILES
            pruned = prune_cache(CACHE_DIR, max_age_days=CACHE_MAX_AGE_DAYS, max_files=CACHE_MAX_FILES)
            if pruned.get("deleted", 0) > 0:
                logger.info("[NIGHTLY] Cache pruned: deleted=%s remaining=%s", pruned.get("deleted"), pruned.get("remaining"))
        except Exception as e:
            logger.warning("[NIGHTLY] Cache prune failed (non-fatal): %s", e)

        # Phase 8.7: Load symbols from tiered universe manifest
        from pathlib import Path
        from app.core.universe.universe_manager import get_symbols_for_cycle, load_universe_manifest
        from app.core.universe.universe_state_store import UniverseStateStore

        repo = Path(__file__).resolve().parents[3]
        manifest_path = repo / "artifacts" / "config" / "universe.json"
        manifest = load_universe_manifest(manifest_path)
        state_store = UniverseStateStore(repo / "artifacts" / "state" / "universe_state.json")
        now_utc = datetime.now(timezone.utc)
        symbols = get_symbols_for_cycle(manifest, now_utc, state_store)
        if not symbols:
            from app.api.data_health import UNIVERSE_SYMBOLS
            symbols = list(UNIVERSE_SYMBOLS)
            logger.info("[NIGHTLY] No universe tiers due; falling back to UNIVERSE_SYMBOLS (%d symbols)", len(symbols))

        if config.max_symbols and config.max_symbols < len(symbols):
            symbols = symbols[:config.max_symbols]
            logger.info("[NIGHTLY] Limited to %d symbols", config.max_symbols)
        
        if not symbols:
            result["error"] = "No symbols in universe"
            return result

        # Phase 8.8: Budget + batch planner
        from app.core.eval.evaluation_budget import EvaluationBudget
        from app.core.eval.batch_planner import plan_batches
        from app.core.config.eval_config import EVAL_BATCH_SIZE, EVAL_MAX_SYMBOLS_PER_CYCLE

        budget = EvaluationBudget.from_config(started_at=datetime.now(timezone.utc))
        symbols = budget.trim_symbols(symbols)

        # Phase 9.0: Universe quality gates (cheap-first, before chain pipeline)
        gate_skips: List[Dict[str, Any]] = []
        symbols_to_evaluate = symbols
        try:
            from app.core.universe.universe_quality_gates import evaluate_universe_quality, GateDecision
            from app.core.config.universe_gates_config import get_gate_config, resolve_gate_config_for_symbol, get_symbol_gate_override
            from app.core.data.symbol_snapshot_service import get_snapshots_batch
            from app.core.symbols.data_dependencies import compute_dependency_lists
            from app.core.environment.market_calendar import trading_days_since

            gate_cfg = get_gate_config()
            if gate_cfg.get("enabled", True):
                snapshots = get_snapshots_batch(symbols, derive_avg_stock_volume_20d=True, use_cache=True)
                symbols_to_evaluate = []
                for sym in symbols:
                    snap = snapshots.get(sym)
                    snap_dict = snap.to_dict() if snap else {}
                    sym_dict = {
                        "symbol": sym,
                        "price": snap_dict.get("price"),
                        "bid": snap_dict.get("bid"),
                        "ask": snap_dict.get("ask"),
                        "volume": snap_dict.get("volume"),
                        "iv_rank": snap_dict.get("iv_rank"),
                        "quote_date": snap_dict.get("quote_date"),
                        "avg_stock_volume_20d": snap_dict.get("avg_stock_volume_20d"),
                        "avg_option_volume_20d": snap_dict.get("avg_option_volume_20d"),
                        "fetched_at": snap_dict.get("quote_as_of") or snap_dict.get("core_as_of"),
                    }
                    req_miss, opt_miss, req_stale, data_as_of = compute_dependency_lists(
                        sym_dict, max_stale_trading_days=gate_cfg.get("data_stale_days_block", 2)
                    )
                    quote_date = sym_dict.get("quote_date")
                    stale_days = None
                    if quote_date:
                        try:
                            from datetime import date
                            s = str(quote_date).strip()[:10]
                            if len(s) >= 10:
                                d = date(int(s[:4]), int(s[5:7]), int(s[8:10]))
                                stale_days = trading_days_since(d)
                        except (ValueError, IndexError, TypeError):
                            pass
                    data_sufficiency = {
                        "required_data_missing": req_miss,
                        "required_data_stale": req_stale,
                        "stale_days": stale_days,
                    }
                    core_snapshot = {
                        "price": snap_dict.get("price"),
                        "bid": snap_dict.get("bid"),
                        "ask": snap_dict.get("ask"),
                        "volume": snap_dict.get("volume"),
                        "avg_stock_volume_20d": snap_dict.get("avg_stock_volume_20d"),
                        "quote_date": snap_dict.get("quote_date"),
                    }
                    gate_cfg_sym = resolve_gate_config_for_symbol(manifest, sym)
                    sym_override = get_symbol_gate_override(manifest, sym)
                    decision = evaluate_universe_quality(
                        sym, core_snapshot, None, data_sufficiency, gate_cfg_sym, sym_override
                    )
                    if decision.status == "SKIP":
                        gate_skips.append({
                            "symbol": sym,
                            "reasons": decision.reasons,
                            "metrics": decision.metrics,
                        })
                        logger.info("[NIGHTLY] Gate SKIP %s: %s", sym, decision.reasons)
                    else:
                        symbols_to_evaluate.append(sym)
                if gate_skips:
                    logger.info("[NIGHTLY] Universe gates: skipped %d/%d symbols", len(gate_skips), len(symbols))
        except Exception as e:
            logger.warning("[NIGHTLY] Universe gates failed (non-fatal, evaluating all): %s", e)
            symbols_to_evaluate = symbols

        batches = plan_batches(symbols_to_evaluate, EVAL_BATCH_SIZE)
        staged_results: list = []
        exposure_summary = None
        budget_stopped = False

        for batch in batches:
            if budget.should_stop_for_time():
                logger.warning("[NIGHTLY] Budget stop: time cap reached; processed %d/%d", budget.symbols_processed, len(symbols))
                budget_stopped = True
                break
            from app.core.eval.staged_evaluator import evaluate_universe_staged, StagedEvaluationResult
            staged_out = evaluate_universe_staged(batch, top_k=config.stage2_top_k)
            if not isinstance(staged_out, StagedEvaluationResult):
                raise TypeError("evaluate_universe_staged must return StagedEvaluationResult")
            staged_results.extend(staged_out.results)
            exposure_summary = staged_out.exposure_summary
            budget.record_batch(len(batch), endpoints_used=["cores", "strikes", "iv_rank"])

        if budget_stopped:
            result["budget_stopped"] = True
            result["budget_warning"] = "Budget stop: time cap reached; processed %d/%d" % (budget.symbols_processed, len(symbols))

        # Phase 8.8: Log budget + cache stats
        try:
            from app.core.data.cache_store import cache_stats
            cs = cache_stats()
            logger.info("[NIGHTLY] Budget: %s | Cache: hit_rate=%.1f%%", budget.budget_status(), cs.get("cache_hit_rate_pct", 0))
        except Exception:
            pass
        
        # Build summary
        duration = time.time() - start_time
        completed_at = datetime.now(timezone.utc).isoformat()
        
        # Count verdicts
        eligible_list = [r for r in staged_results if r.verdict == "ELIGIBLE"]
        hold_list = [r for r in staged_results if r.verdict == "HOLD"]
        block_list = [r for r in staged_results if r.verdict == "BLOCKED"]
        
        # Count stages
        stage1_pass = sum(1 for r in staged_results if r.stage_reached.value in ("STAGE1_ONLY", "STAGE2_CHAIN") and r.stage1 and r.stage1.stock_verdict.value == "QUALIFIED")
        stage2_pass = sum(1 for r in staged_results if r.stage_reached.value == "STAGE2_CHAIN")
        
        # Get regime/risk from first eligible or any result
        regime = None
        risk_posture = None
        for r in staged_results:
            if r.regime:
                regime = r.regime
            if r.risk:
                risk_posture = r.risk
            if regime and risk_posture:
                break
        
        # Convert to dicts for storage
        symbols_data = [r.to_dict() for r in staged_results]
        top_candidates = sorted(
            [r.to_dict() for r in eligible_list],
            key=lambda x: x.get("score", 0),
            reverse=True
        )[:10]
        top_holds = sorted(
            [r.to_dict() for r in hold_list],
            key=lambda x: x.get("score", 0),
            reverse=True
        )[:10]
        
        # Create EvaluationRunFull (correlation_id for diagnostics)
        run = EvaluationRunFull(
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            status="COMPLETED",
            correlation_id=run_id,
            duration_seconds=round(duration, 2),
            total=len(symbols),
            evaluated=len(staged_results),
            eligible=len(eligible_list),
            shortlisted=sum(1 for r in eligible_list if r.score >= 70),
            stage1_pass=stage1_pass,
            stage2_pass=stage2_pass,
            holds=len(hold_list),
            blocks=len(block_list),
            regime=regime,
            risk_posture=risk_posture,
            source="nightly",
            symbols=symbols_data,
            top_candidates=top_candidates,
            top_holds=top_holds,
            alerts=[],  # Nightly doesn't generate real-time alerts
            alerts_count=0,
            exposure_summary=exposure_summary.to_dict() if exposure_summary else None,
        )
        
        # Persist
        save_run(run)
        update_latest_pointer(run_id, completed_at)
        
        # Build Slack summary (Phase 8.8/8.9: cache hit rate, requests_estimated, top endpoint)
        cache_hit_rate = None
        top_endpoint_hit_rate = None
        try:
            from app.core.data.cache_store import cache_stats, cache_stats_by_endpoint
            cs = cache_stats()
            cache_hit_rate = cs.get("cache_hit_rate_pct")
            by_ep = cache_stats_by_endpoint()
            if by_ep:
                best = max(by_ep.items(), key=lambda x: x[1].get("hits", 0) + x[1].get("misses", 0))
                ep_name, ep_stats = best
                rate = ep_stats.get("hit_rate_pct", 0)
                top_endpoint_hit_rate = f"top_ep={ep_name} {rate:.0f}%"
        except Exception:
            pass
        # Phase 9.0: Gate skips summary
        gate_skips_total = len(symbols)
        gate_skips_count = len(gate_skips)
        gate_reasons_summary = None
        if gate_skips:
            reason_counts: Dict[str, int] = {}
            for s in gate_skips:
                for r in s.get("reasons", []):
                    reason_counts[r] = reason_counts.get(r, 0) + 1
            gate_reasons_summary = ", ".join(
                f"{r}={c}" for r, c in sorted(reason_counts.items(), key=lambda x: -x[1])[:5]
            )
        summary = NightlySummary(
            run_id=run_id,
            timestamp=completed_at,
            regime=regime,
            risk_posture=risk_posture,
            duration_seconds=duration,
            universe_total=len(symbols),
            evaluated=len(staged_results),
            stage1_pass=stage1_pass,
            stage2_pass=stage2_pass,
            eligible=len(eligible_list),
            holds=len(hold_list),
            blocks=len(block_list),
            cache_hit_rate_pct=cache_hit_rate,
            requests_estimated=budget.requests_estimated,
            gate_skips_count=gate_skips_count,
            gate_skips_total=gate_skips_total,
            gate_skip_reasons_summary=gate_reasons_summary,
            top_endpoint_hit_rate=top_endpoint_hit_rate,
            top_eligible=top_candidates,
            top_holds=top_holds,
        )
        
        # Send Slack notification
        slack_sent, slack_msg = send_nightly_slack(summary, config.slack_webhook_url)
        
        # Store in-app notification if Slack not sent
        if not slack_sent:
            _store_in_app_notification(run_id, summary, slack_msg)
        
        # Check journal trades for stop/target breaches and emit alerts
        _check_journal_stops_targets(config.slack_webhook_url)
        
        # Run deterministic exit rules (CSP/CC) with EOD snapshot; write alerts and next_actions
        exit_rule_summary = _run_exit_rules_for_journal(config.slack_webhook_url)
        if exit_rule_summary:
            result["exit_rules"] = exit_rule_summary
        
        result.update({
            "success": True,
            "completed_at": completed_at,
            "duration_seconds": duration,
            "counts": {
                "total": len(symbols),
                "evaluated": len(staged_results),
                "stage1_pass": stage1_pass,
                "stage2_pass": stage2_pass,
                "eligible": len(eligible_list),
                "holds": len(hold_list),
                "blocks": len(block_list),
            },
            "slack_sent": slack_sent,
            "slack_message": slack_msg,
        })
        
        logger.info(
            "[NIGHTLY] Completed: %d symbols, %d eligible, %d holds, %.1fs, slack=%s",
            len(symbols), len(eligible_list), len(hold_list), duration, slack_sent
        )
        print(f"[NIGHTLY] Completed: {len(eligible_list)} eligible, {len(hold_list)} holds, Slack: {slack_msg}")

        # Phase 8.8: Run health checks (wall time, cache hit rate)
        try:
            from app.core.system.watchdog import run_watchdog_checks
            cycle_min = manifest.get("cycle_minutes") or 30
            ep_stats = None
            try:
                from app.core.data.cache_store import cache_stats_by_endpoint
                ep_stats = cache_stats_by_endpoint()
            except Exception:
                pass
            run_watchdog_checks(
                last_run_timestamp=None,
                interval_minutes=int(cycle_min),
                wall_time_sec=duration,
                cache_hit_rate_pct=cache_hit_rate,
                requests_estimated=budget.requests_estimated,
                max_requests_estimate=budget.max_requests_estimate,
                cache_stats_by_endpoint=ep_stats,
            )
        except Exception:
            pass
        
    except Exception as e:
        logger.exception("[NIGHTLY] Evaluation failed: %s", e)
        result["error"] = str(e)
        
        # Try to persist failed run
        try:
            failed_run = EvaluationRunFull(
                run_id=run_id,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                status="FAILED",
                duration_seconds=time.time() - start_time,
                source="nightly",
                error_summary=str(e),
                errors=[str(e)],
            )
            save_run(failed_run)
        except Exception:
            pass
    
    return result


def _check_journal_stops_targets(slack_webhook_url: Optional[str] = None) -> None:
    """Check open journal trades for stop/target breaches; store alerts and optionally send to Slack."""
    try:
        from app.core.journal.alerts import check_stops_and_targets
        from app.core.journal.store import _get_journal_dir
        import json
        
        alerts_list = check_stops_and_targets()
        if not alerts_list:
            return
        
        out_dir = _get_journal_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        alerts_path = out_dir / "alerts.jsonl"
        for a in alerts_list:
            record = {
                "trade_id": a.trade_id,
                "symbol": a.symbol,
                "alert_type": a.alert_type,
                "message": a.message,
                "level": a.level,
                "current_price": a.current_price,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(alerts_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            logger.info("[NIGHTLY] Journal alert: %s", a.message)
            
            if slack_webhook_url:
                import requests
                try:
                    requests.post(
                        slack_webhook_url,
                        json={"text": f"*ChakraOps Journal* {a.message}"},
                        timeout=5,
                    )
                except Exception as e:
                    logger.warning("[NIGHTLY] Slack journal alert failed: %s", e)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("[NIGHTLY] Journal stop/target check failed: %s", e)


def _run_exit_rules_for_journal(slack_webhook_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Run deterministic exit rules (CSP/CC) for open journal trades using EOD snapshot.
    Writes alerts to alerts.jsonl, saves next_actions.json, optionally sends Slack summary.
    Returns summary dict with counts and any error message.
    """
    try:
        from app.core.journal.store import (
            list_trades,
            _get_journal_dir,
            get_next_actions,
            save_next_actions,
        )
        from app.core.journal.eod_snapshot import get_eod_snapshot
        from app.core.journal.exit_rules import (
            evaluate_exit_rules,
            best_action_from_alerts,
        )
        import json
    except ImportError as e:
        logger.warning("[NIGHTLY] Exit rules skipped (import failed): %s", e)
        return {"error": str(e), "alerts_count": 0}

    open_trades = [t for t in list_trades(limit=200) if t.remaining_qty > 0]
    if not open_trades:
        return {"alerts_count": 0, "trades_evaluated": 0}

    symbols = list({t.symbol for t in open_trades})
    snapshot_cache: Dict[str, Any] = {}
    for sym in symbols:
        try:
            snapshot_cache[sym] = get_eod_snapshot(sym)
        except Exception as e:
            logger.debug("[NIGHTLY] EOD snapshot %s failed: %s", sym, e)

    all_alerts: List[Any] = []
    for trade in open_trades:
        snapshot = snapshot_cache.get(trade.symbol)
        if snapshot is None:
            continue
        alerts = evaluate_exit_rules(trade, snapshot)
        all_alerts.extend(alerts)

    now = datetime.now(timezone.utc).isoformat()
    out_dir = _get_journal_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    alerts_path = out_dir / "alerts.jsonl"

    for a in all_alerts:
        record = {
            "trade_id": a.trade_id,
            "symbol": a.symbol,
            "alert_type": a.rule_code,
            "message": a.message,
            "severity": a.severity,
            "recommended_action": a.recommended_action,
            "created_at": now,
        }
        with open(alerts_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        logger.info("[NIGHTLY] Exit rule: %s %s - %s", a.rule_code, a.symbol, a.message)

    # Build next_actions: one best action per trade that had alerts
    alerts_by_trade: Dict[str, List[Any]] = {}
    for a in all_alerts:
        alerts_by_trade.setdefault(a.trade_id, []).append(a)
    next_actions = {}
    for trade_id, alerts in alerts_by_trade.items():
        best = best_action_from_alerts(alerts)
        if best:
            next_actions[trade_id] = {
                "action": best["action"],
                "severity": best["severity"],
                "message": best["message"],
                "rule_code": best.get("rule_code"),
                "evaluated_at": now,
            }
    # Trades with no alerts get no entry (UI will show nothing or "—")
    save_next_actions(next_actions)

    # Slack summary
    if slack_webhook_url and all_alerts:
        try:
            import requests
            lines = [f"*Exit rules* ({len(all_alerts)} alert(s)):"]
            for a in all_alerts[:5]:
                lines.append(f"• {a.rule_code} {a.symbol}: {a.message[:80]}")
            if len(all_alerts) > 5:
                lines.append(f"… and {len(all_alerts) - 5} more")
            requests.post(
                slack_webhook_url,
                json={"text": "\n".join(lines)},
                timeout=5,
            )
        except Exception as e:
            logger.warning("[NIGHTLY] Slack exit-rules summary failed: %s", e)

    return {
        "alerts_count": len(all_alerts),
        "trades_evaluated": len(open_trades),
        "symbols_with_snapshot": len(snapshot_cache),
    }


def _store_in_app_notification(run_id: str, summary: NightlySummary, slack_msg: str) -> None:
    """Store notification in-app when Slack is not configured."""
    try:
        from app.core.eval.evaluation_store import _ensure_evaluations_dir
        import json
        
        notif_path = _ensure_evaluations_dir() / "notifications.jsonl"
        notification = {
            "type": "nightly_complete",
            "run_id": run_id,
            "timestamp": summary.timestamp,
            "eligible": summary.eligible,
            "holds": summary.holds,
            "slack_status": slack_msg,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        with open(notif_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(notification) + "\n")
        
        logger.info("[NIGHTLY] Stored in-app notification for %s", run_id)
    except Exception as e:
        logger.warning("[NIGHTLY] Failed to store in-app notification: %s", e)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "NightlyConfig",
    "NightlySummary",
    "build_slack_message",
    "build_slack_message_simple",
    "send_nightly_slack",
    "run_nightly_evaluation",
]
