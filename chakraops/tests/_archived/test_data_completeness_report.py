# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Tests for data completeness report."""

import json
import tempfile
from pathlib import Path

import pytest

from app.core.eval.data_completeness_report import (
    build_data_completeness_report,
    write_data_completeness_report,
)


def test_build_report_per_symbol_and_aggregate():
    symbols = [
        {"symbol": "AAPL", "missing_fields": [], "waiver_reason": None, "data_sources": {}},
        {"symbol": "MISS", "missing_fields": ["bid", "ask", "volume"], "waiver_reason": None, "data_sources": {}},
    ]
    report = build_data_completeness_report(symbols)
    assert "per_symbol" in report
    assert "aggregate" in report
    assert len(report["per_symbol"]) == 2
    assert report["aggregate"]["total_symbols"] == 2
    assert report["aggregate"]["pct_missing_bid_ask"] == 50.0
    assert report["aggregate"]["count_missing_bid_ask"] == 1


def test_build_report_waiver_tracked():
    symbols = [
        {"symbol": "W", "missing_fields": [], "waiver_reason": "DERIVED_FROM_OPRA", "data_sources": {"bid": "waived"}},
    ]
    report = build_data_completeness_report(symbols)
    assert report["aggregate"]["count_with_waiver"] == 1
    assert report["per_symbol"][0]["waived_fields"]


def test_write_report_creates_file():
    symbols = [{"symbol": "X", "missing_fields": [], "waiver_reason": None}]
    with tempfile.TemporaryDirectory() as d:
        path = write_data_completeness_report("eval_test_123", symbols, Path(d))
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["aggregate"]["total_symbols"] == 1
        assert len(data["per_symbol"]) == 1
