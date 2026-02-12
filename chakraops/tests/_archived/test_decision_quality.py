# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4 Tests: Decision quality — outcome tagging, derived metrics, analytics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.core.decision_quality.derived import (
    outcome_tag_from_return_on_risk,
    compute_derived_metrics,
)


def test_outcome_tag_win() -> None:
    """Return on risk >= 0.5 -> WIN."""
    assert outcome_tag_from_return_on_risk(0.5) == "WIN"
    assert outcome_tag_from_return_on_risk(1.0) == "WIN"


def test_outcome_tag_scratch() -> None:
    """Return on risk between -0.2 and 0.5 -> SCRATCH."""
    assert outcome_tag_from_return_on_risk(0.0) == "SCRATCH"
    assert outcome_tag_from_return_on_risk(0.49) == "SCRATCH"
    assert outcome_tag_from_return_on_risk(-0.19) == "SCRATCH"


def test_outcome_tag_loss() -> None:
    """Return on risk <= -0.2 -> LOSS."""
    assert outcome_tag_from_return_on_risk(-0.2) == "LOSS"
    assert outcome_tag_from_return_on_risk(-0.5) == "LOSS"


def test_compute_derived_metrics_full() -> None:
    """Derived metrics computed from position + exit when risk_amount explicitly defined."""
    pos = MagicMock()
    pos.opened_at = "2026-01-15"
    pos.strategy = "CSP"
    pos.strike = 500.0
    pos.contracts = 2
    pos.risk_amount_at_entry = 100000.0

    exit_rec = MagicMock()
    exit_rec.exit_date = "2026-02-06"
    exit_rec.realized_pnl = 250.0

    capital = 100000.0
    derived = compute_derived_metrics(pos, exit_rec, capital=capital, risk_amount=100000.0)

    assert derived["time_in_trade_days"] == 22
    assert derived["capital_days_used"] == 100000.0 * 22
    assert derived["return_on_capital"] == 250.0 / 100000.0
    assert derived["return_on_risk"] == 250.0 / 100000.0
    assert derived["return_on_risk_status"] == "KNOWN"
    assert derived["outcome_tag"] == "SCRATCH"


def test_compute_derived_metrics_win() -> None:
    """Large realized PnL -> WIN when risk_amount defined."""
    pos = MagicMock()
    pos.opened_at = "2026-01-15"
    pos.strategy = "CSP"

    exit_rec = MagicMock()
    exit_rec.exit_date = "2026-02-06"
    exit_rec.realized_pnl = 600.0

    capital = 1000.0
    risk_amount = 1000.0
    derived = compute_derived_metrics(pos, exit_rec, capital=capital, risk_amount=risk_amount)

    assert derived["return_on_risk"] == 0.6
    assert derived["outcome_tag"] == "WIN"


def test_compute_derived_metrics_loss() -> None:
    """Negative realized PnL -> LOSS when R <= -0.2 and risk_amount defined."""
    pos = MagicMock()
    pos.opened_at = "2026-01-15"
    pos.strategy = "CSP"

    exit_rec = MagicMock()
    exit_rec.exit_date = "2026-02-06"
    exit_rec.realized_pnl = -300.0

    capital = 1000.0
    risk_amount = 1000.0
    derived = compute_derived_metrics(pos, exit_rec, capital=capital, risk_amount=risk_amount)

    assert derived["return_on_risk"] == -0.3
    assert derived["outcome_tag"] == "LOSS"


def test_compute_derived_metrics_unknown_risk_definition() -> None:
    """Phase 5: When risk_amount missing, return_on_risk=null, outcome_tag=null, status=UNKNOWN."""
    pos = MagicMock()
    pos.opened_at = "2026-01-15"
    pos.risk_amount_at_entry = None

    exit_rec = MagicMock()
    exit_rec.exit_date = "2026-02-06"
    exit_rec.realized_pnl = 100.0

    derived = compute_derived_metrics(pos, exit_rec, capital=1000.0, risk_amount=None)

    assert derived["return_on_risk"] is None
    assert derived["outcome_tag"] is None
    assert derived["return_on_risk_status"] == "UNKNOWN_INSUFFICIENT_RISK_DEFINITION"


def test_compute_derived_metrics_empty_position() -> None:
    """Missing position returns empty derived."""
    derived = compute_derived_metrics(None, MagicMock())
    assert derived["time_in_trade_days"] is None
    assert derived["outcome_tag"] is None


def test_compute_derived_metrics_empty_exit() -> None:
    """Missing exit returns empty derived."""
    derived = compute_derived_metrics(MagicMock(), None)
    assert derived["time_in_trade_days"] is None
    assert derived["outcome_tag"] is None
