#!/usr/bin/env python3
"""
Phase 8.7: Benchmark tool for universe run planning.

Estimates runtime, HTTP calls, and per-hour volume. No external calls.
Planning tool only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 8.7: Estimate universe run metrics (planning tool, no external calls)"
    )
    parser.add_argument(
        "--symbols",
        type=int,
        default=None,
        help="Override symbol count (default: from manifest)",
    )
    parser.add_argument(
        "--max-per-cycle",
        type=int,
        default=None,
        help="Override max symbols per cycle",
    )
    parser.add_argument(
        "--assumed-latency-ms",
        type=int,
        default=800,
        help="Assumed latency per HTTP call in ms (default: 800)",
    )
    parser.add_argument(
        "--endpoints-per-symbol",
        type=int,
        default=3,
        help="HTTP endpoints per symbol (default: 3)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Assumed concurrency (default: 10)",
    )
    parser.add_argument(
        "--cycle-minutes",
        type=float,
        default=None,
        help="Cycle length in minutes (default: from manifest)",
    )
    args = parser.parse_args()

    # Load manifest for defaults
    try:
        from app.core.universe.universe_manager import load_universe_manifest

        repo = Path(__file__).resolve().parents[1]
        manifest_path = repo / "artifacts" / "config" / "universe.json"
        manifest = load_universe_manifest(manifest_path)
    except Exception as e:
        print(f"Warning: could not load manifest: {e}", file=sys.stderr)
        manifest = {}

    total_symbols = args.symbols
    if total_symbols is None:
        total_symbols = 0
        for t in manifest.get("tiers") or []:
            total_symbols += len(t.get("symbols") or [])

    max_per_cycle = args.max_per_cycle
    if max_per_cycle is None:
        max_per_cycle = int(manifest.get("max_symbols_per_cycle") or 25)

    cycle_min = args.cycle_minutes
    if cycle_min is None:
        cycle_min = float(manifest.get("cycle_minutes") or 30)

    symbols_evaluated = min(total_symbols, max_per_cycle)
    calls_per_cycle = symbols_evaluated * args.endpoints_per_symbol
    latency_sec = args.assumed_latency_ms / 1000.0
    naive_sec = calls_per_cycle * latency_sec / max(args.concurrency, 1)
    cycle_sec = cycle_min * 60.0
    per_hour_calls = (calls_per_cycle / cycle_min) * 60.0 if cycle_min > 0 else 0.0

    print("===== Universe Run Benchmark (Phase 8.7) =====")
    print(f"Total symbols in manifest: {total_symbols}")
    print(f"Symbols evaluated per cycle (budgeted): {symbols_evaluated}")
    print(f"HTTP calls per cycle: {calls_per_cycle} (= {symbols_evaluated} x {args.endpoints_per_symbol})")
    print(f"Assumed latency: {args.assumed_latency_ms} ms, concurrency: {args.concurrency}")
    print(f"Naive wall-clock estimate: {naive_sec:.1f} s")
    print(f"Cycle length: {cycle_min} min")
    print(f"Per-hour call estimate: {per_hour_calls:.0f}")

    warn = False
    if naive_sec > 0.25 * cycle_sec:
        print(f"\nWARN: Estimated time ({naive_sec:.1f}s) > 25%% of cycle ({cycle_sec:.0f}s)")
        warn = True
    if per_hour_calls > 5000:
        print(f"\nWARN: Per-hour call count ({per_hour_calls:.0f}) is high")
        warn = True

    if not warn:
        print("\nNo warnings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
