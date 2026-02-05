#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Diff tool for comparing two SignalRunResult JSON files."""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def load_json_file(filepath: Path) -> Dict[str, Any]:
    """Load JSON file and return parsed dict."""
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {filepath}: {e}", file=sys.stderr)
        sys.exit(1)


def candidate_key(candidate: Dict[str, Any]) -> Tuple[str, str, str, float]:
    """Extract candidate key: (symbol, signal_type, expiry, strike)."""
    return (
        candidate["symbol"],
        candidate["signal_type"],
        candidate["expiry"],
        float(candidate["strike"]),
    )


def format_candidate_key(key: Tuple[str, str, str, float]) -> str:
    """Format candidate key for display."""
    symbol, signal_type, expiry, strike = key
    return f"{symbol} {signal_type} {expiry} {strike:.2f}"


def compare_counts(stats1: Dict[str, int], stats2: Dict[str, int]) -> List[str]:
    """Compare statistics and return diff lines."""
    lines = []
    lines.append("=" * 60)
    lines.append("COUNTS DIFF")
    lines.append("=" * 60)

    all_keys = sorted(set(stats1.keys()) | set(stats2.keys()))
    has_diff = False

    for key in all_keys:
        val1 = stats1.get(key, 0)
        val2 = stats2.get(key, 0)
        if val1 != val2:
            has_diff = True
            diff = val2 - val1
            # diff already includes sign via +d (e.g., +1 / -1)
            lines.append(f"  {key:30s} {val1:6d} -> {val2:6d} ({diff:+d})")
        else:
            lines.append(f"  {key:30s} {val1:6d} (unchanged)")

    if not has_diff:
        lines.append("  (no differences)")

    return lines


def compare_candidate_keys(
    candidates1: List[Dict[str, Any]], candidates2: List[Dict[str, Any]]
) -> List[str]:
    """Compare candidate keys and return diff lines."""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("CANDIDATE KEY DIFF")
    lines.append("=" * 60)

    keys1 = {candidate_key(c): c for c in candidates1}
    keys2 = {candidate_key(c): c for c in candidates2}

    only_in_1 = keys1.keys() - keys2.keys()
    only_in_2 = keys2.keys() - keys1.keys()
    in_both = keys1.keys() & keys2.keys()

    if only_in_1:
        lines.append(f"\n  REMOVED ({len(only_in_1)}):")
        for key in sorted(only_in_1):
            lines.append(f"    - {format_candidate_key(key)}")

    if only_in_2:
        lines.append(f"\n  ADDED ({len(only_in_2)}):")
        for key in sorted(only_in_2):
            lines.append(f"    + {format_candidate_key(key)}")

    if not only_in_1 and not only_in_2:
        lines.append("  (no key differences)")

    lines.append(f"\n  IN BOTH: {len(in_both)} candidates")

    return lines, in_both, keys1, keys2


def compare_candidate_fields(
    in_both: Set[Tuple[str, str, str, float]],
    keys1: Dict[Tuple[str, str, str, float], Dict[str, Any]],
    keys2: Dict[Tuple[str, str, str, float], Dict[str, Any]],
) -> List[str]:
    """Compare field-level differences for candidates present in both."""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("FIELD-LEVEL DIFFS (candidates in both)")
    lines.append("=" * 60)

    # Fields to compare (excluding key fields)
    fields_to_compare = [
        "underlying_price",
        "bid",
        "ask",
        "mid",
        "volume",
        "open_interest",
        "delta",
        "iv",
    ]

    diffs_found = False

    for key in sorted(in_both):
        c1 = keys1[key]
        c2 = keys2[key]

        field_diffs = []
        for field in fields_to_compare:
            val1 = c1.get(field)
            val2 = c2.get(field)

            # Handle None comparisons
            if val1 is None and val2 is None:
                continue
            if val1 is None or val2 is None:
                field_diffs.append(f"    {field:20s} {val1} -> {val2}")
            elif isinstance(val1, float) and isinstance(val2, float):
                if abs(val1 - val2) > 0.0001:  # Floating point tolerance
                    field_diffs.append(f"    {field:20s} {val1:.4f} -> {val2:.4f}")
            elif val1 != val2:
                field_diffs.append(f"    {field:20s} {val1} -> {val2}")

        if field_diffs:
            diffs_found = True
            lines.append(f"\n  {format_candidate_key(key)}:")
            lines.extend(field_diffs)

    if not diffs_found:
        lines.append("  (no field differences)")

    return lines


def compare_exclusions(
    exclusions1: List[Dict[str, Any]], exclusions2: List[Dict[str, Any]]
) -> List[str]:
    """Compare exclusions per symbol and return diff lines."""
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("EXCLUSION CODE DIFFS (per symbol)")
    lines.append("=" * 60)

    # Group exclusions by symbol
    exclusions_by_symbol_1: Dict[str, Set[str]] = defaultdict(set)
    exclusions_by_symbol_2: Dict[str, Set[str]] = defaultdict(set)

    for excl in exclusions1:
        symbol = excl.get("data", {}).get("symbol", "UNKNOWN")
        code = excl.get("code", "UNKNOWN")
        exclusions_by_symbol_1[symbol].add(code)

    for excl in exclusions2:
        symbol = excl.get("data", {}).get("symbol", "UNKNOWN")
        code = excl.get("code", "UNKNOWN")
        exclusions_by_symbol_2[symbol].add(code)

    all_symbols = sorted(set(exclusions_by_symbol_1.keys()) | set(exclusions_by_symbol_2.keys()))

    has_diff = False

    for symbol in all_symbols:
        codes1 = exclusions_by_symbol_1.get(symbol, set())
        codes2 = exclusions_by_symbol_2.get(symbol, set())

        if codes1 != codes2:
            has_diff = True
            only_in_1 = codes1 - codes2
            only_in_2 = codes2 - codes1
            in_both = codes1 & codes2

            lines.append(f"\n  {symbol}:")
            if only_in_1:
                lines.append(f"    REMOVED: {', '.join(sorted(only_in_1))}")
            if only_in_2:
                lines.append(f"    ADDED:   {', '.join(sorted(only_in_2))}")
            if in_both:
                lines.append(f"    UNCHANGED: {', '.join(sorted(in_both))}")
        elif codes1:
            lines.append(f"\n  {symbol}: {', '.join(sorted(codes1))} (unchanged)")

    if not has_diff and not all_symbols:
        lines.append("  (no exclusions)")

    return lines


def diff_signals(file1: Path, file2: Path) -> str:
    """Compare two SignalRunResult JSON files and return diff report."""
    data1 = load_json_file(file1)
    data2 = load_json_file(file2)

    # Extract components
    stats1 = data1.get("stats", {})
    stats2 = data2.get("stats", {})
    candidates1 = data1.get("candidates", [])
    candidates2 = data2.get("candidates", [])
    exclusions1 = data1.get("exclusions", [])
    exclusions2 = data2.get("exclusions", [])

    # Build diff report
    lines = []
    lines.append(f"Comparing: {file1.name} vs {file2.name}")
    lines.append("")

    # Counts diff
    lines.extend(compare_counts(stats1, stats2))

    # Candidate key diff
    key_lines, in_both, keys1, keys2 = compare_candidate_keys(candidates1, candidates2)
    lines.extend(key_lines)

    # Field-level diffs
    lines.extend(compare_candidate_fields(in_both, keys1, keys2))

    # Exclusion diffs
    lines.extend(compare_exclusions(exclusions1, exclusions2))

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Diff two SignalRunResult JSON files")
    parser.add_argument("file1", type=Path, help="First JSON file (baseline)")
    parser.add_argument("file2", type=Path, help="Second JSON file (comparison)")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write diff to file instead of stdout",
    )
    args = parser.parse_args()

    # Generate diff
    diff_output = diff_signals(args.file1, args.file2)

    # Output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(diff_output)
        print(f"Diff written to {args.output}")
    else:
        print(diff_output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
