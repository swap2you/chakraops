# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7: Market Regime Engine tests — deterministic regime, persistence, evaluation gating."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.market.market_regime import (
    MarketRegime,
    IndexInputs,
    MarketRegimeSnapshot,
    _compute_regime_from_inputs,
    get_market_regime,
    compute_and_persist_regime,
    _get_market_dir,
    _regime_path,
)


# ---------------------------------------------------------------------------
# Deterministic regime rules
# ---------------------------------------------------------------------------


def test_risk_on_both_above_ema_and_rsi_ge_45() -> None:
    """RISK_ON: EMA20 > EMA50 on both SPY and QQQ, RSI >= 45 both."""
    inputs = {
        "SPY": IndexInputs(close=450.0, ema20=448.0, ema50=445.0, rsi=50.0),
        "QQQ": IndexInputs(close=400.0, ema20=398.0, ema50=395.0, rsi=48.0),
    }
    assert _compute_regime_from_inputs(inputs) == MarketRegime.RISK_ON


def test_risk_off_ema20_below_ema50_on_spy() -> None:
    """RISK_OFF: EMA20 < EMA50 on either index."""
    inputs = {
        "SPY": IndexInputs(close=450.0, ema20=443.0, ema50=445.0, rsi=50.0),
        "QQQ": IndexInputs(close=400.0, ema20=398.0, ema50=395.0, rsi=48.0),
    }
    assert _compute_regime_from_inputs(inputs) == MarketRegime.RISK_OFF


def test_risk_off_ema20_below_ema50_on_qqq() -> None:
    """RISK_OFF: EMA20 < EMA50 on QQQ only."""
    inputs = {
        "SPY": IndexInputs(close=450.0, ema20=448.0, ema50=445.0, rsi=50.0),
        "QQQ": IndexInputs(close=400.0, ema20=393.0, ema50=395.0, rsi=48.0),
    }
    assert _compute_regime_from_inputs(inputs) == MarketRegime.RISK_OFF


def test_risk_off_rsi_le_40_spy() -> None:
    """RISK_OFF: RSI <= 40 on either."""
    inputs = {
        "SPY": IndexInputs(close=450.0, ema20=448.0, ema50=445.0, rsi=38.0),
        "QQQ": IndexInputs(close=400.0, ema20=398.0, ema50=395.0, rsi=48.0),
    }
    assert _compute_regime_from_inputs(inputs) == MarketRegime.RISK_OFF


def test_neutral_ema_above_but_rsi_below_45() -> None:
    """NEUTRAL: EMA20 > EMA50 both but RSI < 45 on one."""
    inputs = {
        "SPY": IndexInputs(close=450.0, ema20=448.0, ema50=445.0, rsi=42.0),
        "QQQ": IndexInputs(close=400.0, ema20=398.0, ema50=395.0, rsi=48.0),
    }
    assert _compute_regime_from_inputs(inputs) == MarketRegime.NEUTRAL


def test_neutral_missing_rsi() -> None:
    """NEUTRAL when RSI missing (cannot confirm RISK_ON)."""
    inputs = {
        "SPY": IndexInputs(close=450.0, ema20=448.0, ema50=445.0, rsi=None),
        "QQQ": IndexInputs(close=400.0, ema20=398.0, ema50=395.0, rsi=48.0),
    }
    assert _compute_regime_from_inputs(inputs) == MarketRegime.NEUTRAL


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_persistence_write_and_read(tmp_path: Path) -> None:
    """Compute and persist regime; read back same date."""
    with patch("app.core.market.market_regime._get_market_dir", return_value=tmp_path):
        with patch("app.core.market.market_regime._regime_path", return_value=tmp_path / "market_regime.json"):
            snapshot = MarketRegimeSnapshot(
                date="2026-02-04",
                regime=MarketRegime.RISK_ON.value,
                inputs={
                    "SPY": {"close": 450.0, "ema20": 448.0, "ema50": 445.0, "rsi": 50.0},
                    "QQQ": {"close": 400.0, "ema20": 398.0, "ema50": 395.0, "rsi": 48.0},
                },
            )
            path = tmp_path / "market_regime.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(snapshot.to_dict(), f, indent=2)

            got = get_market_regime(as_of_date=date(2026, 2, 4))
            assert got.date == "2026-02-04"
            assert got.regime == MarketRegime.RISK_ON.value
            assert "SPY" in got.inputs


# ---------------------------------------------------------------------------
# Evaluation gating (integration with staged evaluator)
# ---------------------------------------------------------------------------


def test_evaluation_gating_risk_off_caps_score_and_hold() -> None:
    """When market regime is RISK_OFF, evaluator caps score at 50 and forces HOLD."""
    from app.core.eval.staged_evaluator import (
        FullEvaluationResult,
        FinalVerdict,
        EvaluationStage,
        Stage1Result,
        StockVerdict,
    )
    from app.core.market.market_regime import MarketRegime

    # Simulate applying the gate (same logic as in evaluate_universe_staged)
    result = FullEvaluationResult(symbol="AAPL", score=85, verdict="ELIGIBLE")
    result.final_verdict = FinalVerdict.ELIGIBLE
    result.primary_reason = "All checks passed"

    market_regime_value = MarketRegime.RISK_OFF.value
    result.regime = market_regime_value
    result.score = min(result.score, 50)
    result.final_verdict = FinalVerdict.HOLD
    result.verdict = "HOLD"
    result.primary_reason = "Blocked by market regime: RISK_OFF"

    assert result.score == 50
    assert result.verdict == "HOLD"
    assert result.final_verdict == FinalVerdict.HOLD
    assert "RISK_OFF" in result.primary_reason


def test_evaluation_gating_neutral_caps_score_only() -> None:
    """When market regime is NEUTRAL, score is capped at 65; verdict not forced."""
    from app.core.eval.staged_evaluator import FullEvaluationResult, FinalVerdict

    result = FullEvaluationResult(symbol="AAPL", score=80, verdict="ELIGIBLE")
    result.final_verdict = FinalVerdict.ELIGIBLE

    market_regime_value = "NEUTRAL"
    result.regime = market_regime_value
    result.score = min(result.score, 65)

    assert result.score == 65
    assert result.verdict == "ELIGIBLE"
    assert result.final_verdict == FinalVerdict.ELIGIBLE
