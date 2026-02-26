# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.5 / R24.5.1: Earnings advisory — ORATS fetch, validation, scaling, no FAIL_/WARN_, earnings not in decision artifact."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.orats.earnings import (
    STATUS_OK,
    STATUS_UNAVAILABLE,
    _as_of_date_ny,
    _calendar_days,
    _is_valid_next_ern,
    _parse_date,
    fetch_earnings_advisory,
    fetch_earnings_advisory_batch,
)


def test_parse_date() -> None:
    assert _parse_date("2026-02-25") == "2026-02-25"
    assert _parse_date("2026-02-25T12:00:00Z") == "2026-02-25"
    assert _parse_date(None) is None
    assert _parse_date("") is None
    assert _parse_date("invalid") is None


def test_parse_date_rejects_0000_00_00() -> None:
    """R24.5.1: Bogus nextErn must be rejected."""
    assert _parse_date("0000-00-00") is None
    assert _parse_date("0000-00-00T00:00:00") is None
    assert _parse_date("  0000-00-00  ") is None


def test_is_valid_next_ern() -> None:
    assert _is_valid_next_ern("2026-02-25") is True
    assert _is_valid_next_ern("2000-01-15") is True
    assert _is_valid_next_ern("0000-00-00") is False
    assert _is_valid_next_ern("") is False
    assert _is_valid_next_ern("2026-00-01") is False  # month 0 invalid
    assert _is_valid_next_ern("2026-01-00") is False  # day 0 invalid


def test_calendar_days() -> None:
    assert _calendar_days("2026-02-25", "2026-02-26") == 1
    assert _calendar_days("2026-02-25", "2026-02-25") == 0
    assert _calendar_days("2026-02-25", "2026-03-01") == 4
    assert _calendar_days("2026-02-25", "2026-02-24") == -1
    assert _calendar_days("", "2026-02-26") is None
    assert _calendar_days("2026-02-25", "") is None


def test_as_of_date_ny() -> None:
    utc = datetime(2026, 2, 25, 18, 0, 0, tzinfo=timezone.utc)
    ny_date = _as_of_date_ny(utc)
    assert ny_date in ("2026-02-25", "2026-02-26")  # depends on DST
    assert ny_date is not None


def test_earnings_advisory_determinism() -> None:
    """Same inputs -> same outputs (no FAIL_/WARN_ in returned dict)."""
    as_of = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
    mock_core = {
        "ticker": "NVDA",
        "nextErn": "2026-02-26",
        "daysToNextErn": 1,
        "impliedEarningsMove": 0.08,
        "quoteDate": "2026-02-25T21:00:00Z",
    }
    with patch("app.core.orats.earnings.fetch_core_snapshot", return_value=mock_core):
        out1 = fetch_earnings_advisory("NVDA", as_of_utc=as_of, token="test-token")
        out2 = fetch_earnings_advisory("NVDA", as_of_utc=as_of, token="test-token")
    assert out1 == out2
    assert out1["earnings_next_date"] == "2026-02-26"
    assert out1["earnings_data_status"] == STATUS_OK
    assert out1["implied_earnings_move_pct"] == 8.0
    # No raw codes
    for v in (out1, out2):
        js = json.dumps(v, default=str)
        assert "FAIL_" not in js
        assert "WARN_" not in js


def test_earnings_advisory_unavailable_without_token() -> None:
    out = fetch_earnings_advisory("AAPL", token="")
    assert out["earnings_data_status"] == STATUS_UNAVAILABLE
    assert "FAIL_" not in json.dumps(out, default=str)
    assert "WARN_" not in json.dumps(out, default=str)


def test_earnings_advisory_batch() -> None:
    with patch("app.core.orats.earnings.fetch_core_snapshot", return_value={}):
        out = fetch_earnings_advisory_batch(["AAPL", "MSFT"], token="x")
    assert "AAPL" in out
    assert "MSFT" in out
    assert out["AAPL"]["earnings_data_status"] == STATUS_UNAVAILABLE  # empty core -> no next_ern


def test_next_ern_0000_00_00_returns_unavailable_and_nulls() -> None:
    """R24.5.1: nextErn=0000-00-00 => status Unavailable, all earnings fields null except earnings_as_of."""
    mock_core = {
        "ticker": "BOGUS",
        "nextErn": "0000-00-00",
        "daysToNextErn": 0,
        "impliedEarningsMove": 0.5,
        "quoteDate": "2026-02-25T21:00:00Z",
    }
    with patch("app.core.orats.earnings.fetch_core_snapshot", return_value=mock_core):
        out = fetch_earnings_advisory("BOGUS", as_of_utc=datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc), token="x")
    assert out["earnings_data_status"] == STATUS_UNAVAILABLE
    assert out["earnings_next_date"] is None
    assert out["earnings_days"] is None
    assert out["implied_earnings_move_pct"] is None
    assert out["earnings_as_of"] == "2026-02-25T21:00:00Z"


def test_implied_move_scaling_r2451() -> None:
    """R24.5.1: 0 < v <= 1 => fraction (pct=value*100); 1 < v <= 50 => percent; else null."""
    as_of = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
    base = {"ticker": "X", "nextErn": "2026-03-01", "daysToNextErn": 4, "quoteDate": "2026-02-25T21:00:00Z"}
    with patch("app.core.orats.earnings.fetch_core_snapshot", return_value={**base, "impliedEarningsMove": 0.072}):
        out = fetch_earnings_advisory("X", as_of_utc=as_of, token="x")
    assert out["implied_earnings_move_pct"] == pytest.approx(7.2)
    with patch("app.core.orats.earnings.fetch_core_snapshot", return_value={**base, "impliedEarningsMove": 7.2}):
        out = fetch_earnings_advisory("X", as_of_utc=as_of, token="x")
    assert out["implied_earnings_move_pct"] == 7.2
    with patch("app.core.orats.earnings.fetch_core_snapshot", return_value={**base, "impliedEarningsMove": 563}):
        out = fetch_earnings_advisory("X", as_of_utc=as_of, token="x")
    assert out["implied_earnings_move_pct"] is None


def test_decision_artifact_earnings_not_persisted() -> None:
    """Earnings advisory fields must not appear in to_dict_persist (code-only; no earnings_next_date etc)."""
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, EarningsInfo
    e = EarningsInfo(
        earnings_days=5,
        earnings_block=False,
        note="Unavailable",
        status_code="EARNINGS_OK",
    )
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": "v2", "run_id": "r1", "pipeline_timestamp": "2026-02-25T12:00:00Z"},
        symbols=[],
        selected_candidates=[],
        earnings_by_symbol={"AAPL": e},
    )
    persisted = artifact.to_dict_persist()
    eb = persisted.get("earnings_by_symbol") or {}
    aapl = eb.get("AAPL") or {}
    assert "earnings_next_date" not in aapl
    assert "implied_earnings_move_pct" not in aapl
    assert "earnings_data_status" not in aapl
    assert "earnings_as_of" not in aapl
    assert "note" not in aapl
    assert "status_code" in aapl
    assert "earnings_days" in aapl
    assert "earnings_block" in aapl


def test_api_response_no_fail_warn_in_earnings(tmp_path: Path) -> None:
    """Persisted decision_latest.json must not contain FAIL_ or WARN_ substrings."""
    from app.core.eval.decision_artifact_v2 import DecisionArtifactV2, EarningsInfo, SymbolEvalSummary
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir, get_evaluation_store_v2
    set_output_dir(tmp_path)
    try:
        sym = SymbolEvalSummary(
            symbol="AAPL",
            verdict="ELIGIBLE",
            final_verdict="ELIGIBLE",
            score=60,
            band="B",
            primary_reason=None,
            primary_reason_codes=[],
            stage_status="RUN",
            stage1_status="PASS",
            stage2_status="PASS",
            provider_status="OK",
            data_freshness=None,
            evaluated_at=None,
            strategy=None,
            price=None,
            expiration=None,
            has_candidates=False,
            candidate_count=0,
        )
        artifact = DecisionArtifactV2(
            metadata={"artifact_version": "v2", "run_id": "r1", "pipeline_timestamp": "2026-02-25T12:00:00Z"},
            symbols=[sym],
            selected_candidates=[],
            earnings_by_symbol={
                "AAPL": EarningsInfo(earnings_days=3, earnings_block=False, note=None, status_code="EARNINGS_OK"),
            },
        )
        store = get_evaluation_store_v2()
        store.set_latest(artifact)
        path = tmp_path / "decision_latest.json"
        assert path.exists()
        raw = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(raw)
        assert "FAIL_" not in text
        assert "WARN_" not in text
    finally:
        reset_output_dir()
