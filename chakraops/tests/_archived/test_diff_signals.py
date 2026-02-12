# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for diff_signals.py tool."""

from __future__ import annotations

from pathlib import Path

import re
import pytest

# Import the diff_signals function directly
import sys

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from scripts.diff_signals import (
    candidate_key,
    compare_candidate_fields,
    compare_candidate_keys,
    compare_counts,
    compare_exclusions,
    diff_signals,
    format_candidate_key,
    load_json_file,
)


class TestDiffSignals:
    """Test diff_signals tool functions."""

    def test_load_json_file(self) -> None:
        """Test loading JSON file."""
        test_dir = Path(__file__).parent.parent  # tests/
        fixture_file = test_dir / "fixtures" / "signals_baseline.json"

        data = load_json_file(fixture_file)
        assert "candidates" in data
        assert "exclusions" in data
        assert "stats" in data

    def test_candidate_key(self) -> None:
        """Test candidate key extraction."""
        candidate = {
            "symbol": "AAPL",
            "signal_type": "CSP",
            "expiry": "2026-02-20",
            "strike": 145.0,
        }
        key = candidate_key(candidate)
        assert key == ("AAPL", "CSP", "2026-02-20", 145.0)

    def test_format_candidate_key(self) -> None:
        """Test candidate key formatting."""
        key = ("AAPL", "CSP", "2026-02-20", 145.0)
        formatted = format_candidate_key(key)
        assert formatted == "AAPL CSP 2026-02-20 145.00"

    def test_compare_counts(self) -> None:
        """Test counts comparison."""
        stats1 = {
            "total_candidates": 2,
            "csp_candidates": 1,
            "cc_candidates": 1,
        }
        stats2 = {
            "total_candidates": 3,
            "csp_candidates": 2,
            "cc_candidates": 1,
        }

        lines = compare_counts(stats1, stats2)
        output = "\n".join(lines)

        assert "total_candidates" in output
        # Be resilient to spacing/alignment; assert the directional diff exists
        assert re.search(r"total_candidates\s+2\s+->\s+3", output) is not None
        assert "csp_candidates" in output
        assert "cc_candidates" in output

    def test_compare_candidate_keys(self) -> None:
        """Test candidate key comparison."""
        candidates1 = [
            {
                "symbol": "AAPL",
                "signal_type": "CSP",
                "expiry": "2026-02-20",
                "strike": 145.0,
            },
            {
                "symbol": "AAPL",
                "signal_type": "CC",
                "expiry": "2026-02-20",
                "strike": 155.0,
            },
        ]

        candidates2 = [
            {
                "symbol": "AAPL",
                "signal_type": "CSP",
                "expiry": "2026-02-20",
                "strike": 145.0,
            },
            {
                "symbol": "MSFT",
                "signal_type": "CSP",
                "expiry": "2026-02-20",
                "strike": 390.0,
            },
        ]

        lines, in_both, keys1, keys2 = compare_candidate_keys(candidates1, candidates2)
        output = "\n".join(lines)

        # Should show removed CC and added MSFT
        assert "REMOVED" in output or "ADDED" in output
        assert len(in_both) == 1  # AAPL CSP should be in both

    def test_compare_candidate_fields(self) -> None:
        """Test field-level comparison."""
        key = ("AAPL", "CSP", "2026-02-20", 145.0)
        keys1 = {
            key: {
                "symbol": "AAPL",
                "signal_type": "CSP",
                "expiry": "2026-02-20",
                "strike": 145.0,
                "bid": 2.5,
                "ask": 2.6,
                "mid": 2.55,
                "volume": 1000,
            }
        }
        keys2 = {
            key: {
                "symbol": "AAPL",
                "signal_type": "CSP",
                "expiry": "2026-02-20",
                "strike": 145.0,
                "bid": 2.6,
                "ask": 2.7,
                "mid": 2.65,
                "volume": 1200,
            }
        }

        lines = compare_candidate_fields({key}, keys1, keys2)
        output = "\n".join(lines)

        assert "bid" in output
        assert "ask" in output
        assert "mid" in output
        assert "volume" in output

    def test_compare_exclusions(self) -> None:
        """Test exclusion comparison."""
        exclusions1 = [
            {
                "code": "NO_LIQUID_PUTS",
                "message": "MSFT: No liquid PUTs",
                "data": {"symbol": "MSFT"},
            }
        ]
        exclusions2 = [
            {
                "code": "NO_STRIKES_IN_OTM_RANGE",
                "message": "MSFT: No strikes in range",
                "data": {"symbol": "MSFT"},
            }
        ]

        lines = compare_exclusions(exclusions1, exclusions2)
        output = "\n".join(lines)

        assert "MSFT" in output
        assert "NO_LIQUID_PUTS" in output or "NO_STRIKES_IN_OTM_RANGE" in output

    def test_diff_signals_integration(self) -> None:
        """Test full diff_signals integration with fixture files."""
        test_dir = Path(__file__).parent.parent  # tests/
        file1 = test_dir / "fixtures" / "signals_baseline.json"
        file2 = test_dir / "fixtures" / "signals_comparison.json"

        diff_output = diff_signals(file1, file2)

        # Verify output contains expected sections
        assert "COUNTS DIFF" in diff_output
        assert "CANDIDATE KEY DIFF" in diff_output
        assert "FIELD-LEVEL DIFFS" in diff_output
        assert "EXCLUSION CODE DIFFS" in diff_output

        # Verify specific differences are reported
        assert "total_candidates" in diff_output
        assert "AAPL CSP" in diff_output  # Should be in both
        assert "MSFT" in diff_output  # Should be added

    def test_diff_signals_identical(self) -> None:
        """Test diff_signals with identical files."""
        test_dir = Path(__file__).parent.parent  # tests/
        file1 = test_dir / "fixtures" / "signals_baseline.json"
        file2 = test_dir / "fixtures" / "signals_baseline.json"

        diff_output = diff_signals(file1, file2)

        # Should show no differences
        assert "(no differences)" in diff_output or "(unchanged)" in diff_output

    def test_diff_signals_deterministic(self) -> None:
        """Test that diff output is deterministic."""
        test_dir = Path(__file__).parent.parent  # tests/
        file1 = test_dir / "fixtures" / "signals_baseline.json"
        file2 = test_dir / "fixtures" / "signals_comparison.json"

        diff1 = diff_signals(file1, file2)
        diff2 = diff_signals(file1, file2)

        # Should be identical
        assert diff1 == diff2

    def test_diff_signals_reverse_order(self) -> None:
        """Test that diff works in reverse order (file2 vs file1)."""
        test_dir = Path(__file__).parent.parent  # tests/
        file1 = test_dir / "fixtures" / "signals_baseline.json"
        file2 = test_dir / "fixtures" / "signals_comparison.json"

        diff_forward = diff_signals(file1, file2)
        diff_reverse = diff_signals(file2, file1)

        # Both should produce valid output
        assert len(diff_forward) > 0
        assert len(diff_reverse) > 0

        # Counts should be reversed
        assert re.search(r"total_candidates\s+2\s+->\s+3", diff_forward) is not None
        assert re.search(r"total_candidates\s+3\s+->\s+2", diff_reverse) is not None


__all__ = ["TestDiffSignals"]
