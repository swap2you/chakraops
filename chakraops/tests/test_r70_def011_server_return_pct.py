# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-DEF-011: expected_return_pct is server-authored on candidates."""

from __future__ import annotations

from app.core.eval.decision_artifact_v2 import CandidateRow


def test_candidate_row_expected_return_pct_server_side() -> None:
    row = CandidateRow(
        symbol="AAPL",
        strategy="CSP",
        expiry="2099-12-19",
        strike=100.0,
        delta=-0.25,
        credit_estimate=1.5,
        max_loss=9850.0,
    )
    d = row.to_dict()
    assert d["expected_return_pct"] == 1.5  # 1.5/100*100


def test_candidate_row_expected_return_pct_missing_when_incomplete() -> None:
    row = CandidateRow(
        symbol="AAPL",
        strategy="CSP",
        expiry=None,
        strike=None,
        delta=None,
        credit_estimate=1.5,
        max_loss=None,
    )
    assert row.to_dict()["expected_return_pct"] is None
