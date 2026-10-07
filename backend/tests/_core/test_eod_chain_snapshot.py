# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for EOD chain snapshot job (Phase 3.1.3): Friday run, holiday skip, weekend skip."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.core.eval.eod_chain_snapshot import (
    get_eod_chain_dir,
    run_eod_chain_snapshot,
    should_run_eod_chain_today,
)


# --- should_run_eod_chain_today (schedule simulation) ---


def test_should_run_eod_chain_today_friday():
    """Friday is a trading day when not a holiday; job runs normally."""
    # Friday 2026-02-13 is not a holiday
    friday = date(2026, 2, 13)
    assert friday.weekday() == 4  # Friday
    assert should_run_eod_chain_today(friday) is True


def test_should_run_eod_chain_today_weekend_skip():
    """Saturday and Sunday: job does not run."""
    sat = date(2026, 2, 14)  # Saturday
    sun = date(2026, 2, 15)  # Sunday
    assert should_run_eod_chain_today(sat) is False
    assert should_run_eod_chain_today(sun) is False


def test_should_run_eod_chain_today_holiday_skip():
    """Holidays: job does nothing."""
    new_years = date(2026, 1, 1)
    christmas = date(2026, 12, 25)
    assert should_run_eod_chain_today(new_years) is False
    assert should_run_eod_chain_today(christmas) is False


def test_get_eod_chain_dir():
    """EOD chain artifacts go under artifacts/runs/YYYY-MM-DD/eod_chain/."""
    d = date(2026, 2, 10)
    path = get_eod_chain_dir(d)
    assert path.name == "eod_chain"
    assert path.parent.name == "2026-02-10"
    assert "artifacts" in str(path)
    assert "runs" in str(path)


def test_run_eod_chain_snapshot_no_chain_log_warning_only(tmp_path):
    """If no chain available for a symbol, log warning and continue (do not block)."""
    with patch("app.core.eval.eod_chain_snapshot._artifacts_runs_root", return_value=tmp_path):
        with patch("app.core.options.orats_chain_pipeline.fetch_base_chain") as m_fetch:
            # One symbol returns empty (no chain), one returns data
            from app.core.options.orats_chain_pipeline import BaseContract

            m_fetch.side_effect = [
                ([], None, "No strikes data", 0),  # no chain for first symbol
                (
                    [
                        BaseContract(
                            symbol="AAPL",
                            expiration=date(2026, 3, 20),
                            strike=150.0,
                            option_type="PUT",
                            dte=30,
                            delta=-0.3,
                            stock_price=175.0,
                        ),
                    ],
                    175.0,
                    None,
                    1,
                ),
            ]
            result = run_eod_chain_snapshot(date(2026, 2, 10), ["NOCHAIN", "AAPL"])
    assert result["written"] == 1
    assert result["skipped"] == 1
    assert result["errors"] == 0
    eod_dir = tmp_path / "2026-02-10" / "eod_chain"
    assert eod_dir.is_dir()
    assert (eod_dir / "AAPL_chain_20260210_1600ET.json").exists()
    assert not (eod_dir / "NOCHAIN_chain_20260210_1600ET.json").exists()
