#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ChakraOps Evaluation CLI.

Usage:
    python -m chakraops.run_evaluation --mode nightly --asof last_close
    python -m chakraops.run_evaluation --mode nightly --dry-run
    python -m chakraops.run_evaluation --mode manual
    python -m chakraops.run_evaluation --help

Environment variables:
    NIGHTLY_EVAL_TIME       - Time to run (HH:MM, 24h format, default: 19:00)
    NIGHTLY_EVAL_TZ         - Timezone (default: America/New_York)
    NIGHTLY_MAX_SYMBOLS     - Max symbols to evaluate (default: all)
    NIGHTLY_STAGE2_TOP_K    - Top K for stage 2 (default: 20)
    SLACK_WEBHOOK_URL       - Slack webhook for notifications
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ChakraOps Evaluation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "--mode",
        choices=["nightly", "manual", "test"],
        default="nightly",
        help="Evaluation mode (default: nightly)",
    )
    
    parser.add_argument(
        "--asof",
        default="last_close",
        help="Reference point: 'last_close', 'now', or ISO timestamp (default: last_close)",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate evaluation without running",
    )
    
    parser.add_argument(
        "--no-slack",
        action="store_true",
        help="Skip Slack notification",
    )
    
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Limit number of symbols to evaluate",
    )
    
    parser.add_argument(
        "--stage2-top-k",
        type=int,
        default=20,
        help="Number of top candidates for stage 2 (default: 20)",
    )
    
    parser.add_argument(
        "--use-universe",
        action="store_true",
        help="Phase 8.7: Use tiered universe manifest for symbol list (manual mode)",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print(f"ChakraOps Evaluation CLI")
    print(f"========================")
    print(f"Mode: {args.mode}")
    print(f"As-of: {args.asof}")
    print(f"Dry run: {args.dry_run}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print()
    
    try:
        if args.mode == "nightly":
            return run_nightly_mode(args)
        elif args.mode == "manual":
            return run_manual_mode(args)
        elif args.mode == "test":
            return run_test_mode(args)
        else:
            print(f"Unknown mode: {args.mode}", file=sys.stderr)
            return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130
    except Exception as e:
        logger.exception("Evaluation failed: %s", e)
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_nightly_mode(args: argparse.Namespace) -> int:
    """Run nightly evaluation."""
    from app.core.eval.nightly_evaluation import NightlyConfig, run_nightly_evaluation
    
    config = NightlyConfig.from_env()
    
    # Override from CLI args
    config.dry_run = args.dry_run
    if args.max_symbols:
        config.max_symbols = args.max_symbols
    if args.stage2_top_k:
        config.stage2_top_k = args.stage2_top_k
    if args.no_slack:
        config.slack_webhook_url = None
    
    print(f"Configuration:")
    print(f"  eval_time: {config.eval_time}")
    print(f"  timezone: {config.timezone}")
    print(f"  max_symbols: {config.max_symbols or 'all'}")
    print(f"  stage2_top_k: {config.stage2_top_k}")
    print(f"  slack: {'disabled' if args.no_slack else ('configured' if config.slack_webhook_url else 'not configured')}")
    print()
    
    result = run_nightly_evaluation(config=config, asof=args.asof)
    
    print()
    print(f"Result:")
    print(f"  run_id: {result.get('run_id')}")
    print(f"  success: {result.get('success')}")
    
    if result.get("counts"):
        counts = result["counts"]
        print(f"  evaluated: {counts.get('evaluated')}")
        print(f"  stage1_pass: {counts.get('stage1_pass')}")
        print(f"  stage2_pass: {counts.get('stage2_pass')}")
        print(f"  eligible: {counts.get('eligible')}")
        print(f"  holds: {counts.get('holds')}")
        print(f"  blocks: {counts.get('blocks')}")
    
    if result.get("slack_sent"):
        print(f"  slack: sent")
    elif result.get("slack_message"):
        print(f"  slack: {result.get('slack_message')}")
    
    if result.get("error"):
        print(f"  error: {result.get('error')}")
    
    return 0 if result.get("success") else 1


def run_manual_mode(args: argparse.Namespace) -> int:
    """Run manual evaluation (same as API trigger)."""
    from pathlib import Path

    from app.core.eval.universe_evaluator import run_universe_evaluation_staged

    if getattr(args, "use_universe", False):
        try:
            from app.core.universe.universe_manager import get_symbols_for_cycle, load_universe_manifest
            from app.core.universe.universe_state_store import UniverseStateStore
            repo = Path(__file__).resolve().parent
            manifest = load_universe_manifest(repo / "artifacts" / "config" / "universe.json")
            state_store = UniverseStateStore(repo / "artifacts" / "state" / "universe_state.json")
            now_utc = datetime.now(timezone.utc)
            symbols = get_symbols_for_cycle(manifest, now_utc, state_store)
            if not symbols:
                from app.api.data_health import UNIVERSE_SYMBOLS
                symbols = list(UNIVERSE_SYMBOLS)
        except Exception:
            from app.api.data_health import UNIVERSE_SYMBOLS
            symbols = list(UNIVERSE_SYMBOLS)
    else:
        from app.api.data_health import UNIVERSE_SYMBOLS
        symbols = list(UNIVERSE_SYMBOLS)
    if args.max_symbols:
        symbols = symbols[:args.max_symbols]
    
    print(f"Running manual evaluation for {len(symbols)} symbols...")
    
    if args.dry_run:
        print("Dry run - skipping actual evaluation")
        return 0
    
    result = run_universe_evaluation_staged(symbols, use_staged=True)
    
    print(f"Result: {result.evaluation_state}")
    print(f"  eligible: {result.eligible}")
    print(f"  evaluated: {result.evaluated}")
    
    return 0


def run_test_mode(args: argparse.Namespace) -> int:
    """Run test mode - builds Slack message without sending."""
    from app.core.eval.nightly_evaluation import NightlySummary, build_slack_message_simple
    
    print("Building test Slack message...")
    
    # Create a mock summary
    summary = NightlySummary(
        run_id="test_run_123",
        timestamp=datetime.now(timezone.utc).isoformat(),
        regime="NEUTRAL",
        risk_posture="MODERATE",
        duration_seconds=45.2,
        universe_total=50,
        evaluated=50,
        stage1_pass=35,
        stage2_pass=20,
        eligible=5,
        holds=25,
        blocks=5,
        top_eligible=[
            {"symbol": "AAPL", "score": 85, "primary_reason": "Chain evaluated, contract selected"},
            {"symbol": "MSFT", "score": 82, "primary_reason": "Chain evaluated, contract selected"},
            {"symbol": "GOOGL", "score": 78, "primary_reason": "Chain evaluated, contract selected"},
        ],
        top_holds=[
            {"symbol": "TSLA", "primary_reason": "DATA_INCOMPLETE: missing delta, open_interest"},
            {"symbol": "NVDA", "primary_reason": "Low liquidity: spread > 10%"},
        ],
    )
    
    message = build_slack_message_simple(summary)
    
    print()
    print("Slack message preview:")
    print("-" * 40)
    print(message)
    print("-" * 40)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
