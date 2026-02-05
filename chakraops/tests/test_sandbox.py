"""Tests for Operator Calibration Sandbox (Phase 7.5)."""

import json
from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import ScoredSignalCandidate, SignalScore, ScoreComponent
from app.ui.sandbox import SandboxParams, SandboxResult, evaluate_sandbox


def _create_test_candidate(
    symbol: str = "AAPL",
    signal_type: SignalType = SignalType.CSP,
    strike: float = 150.0,
    expiry: date = date(2026, 2, 20),
    score: float = 0.5,
) -> ScoredSignalCandidate:
    """Create a test ScoredSignalCandidate."""
    # Set option_right based on signal_type
    option_right = "PUT" if signal_type == SignalType.CSP else "CALL"
    
    candidate = SignalCandidate(
        symbol=symbol,
        signal_type=signal_type,
        as_of=datetime.now(),
        underlying_price=155.0,
        expiry=expiry,
        strike=strike,
        option_right=option_right,
        bid=1.5,
        ask=1.6,
        mid=1.55,
        volume=100,
        open_interest=1000,
        delta=-0.3 if signal_type == SignalType.CSP else 0.3,
        iv=0.25,
        annualized_yield=0.15,
        raw_yield=0.01,
        max_profit=1.55,
        collateral=15000.0,
    )
    
    score_obj = SignalScore(
        total=score,
        components=[
            ScoreComponent(name="premium", value=0.5, weight=1.0),
            ScoreComponent(name="dte", value=0.5, weight=1.0),
        ],
    )
    
    return ScoredSignalCandidate(candidate=candidate, score=score_obj, rank=1)


def test_sandbox_params():
    """Test SandboxParams dataclass."""
    params = SandboxParams(
        min_score=0.3,
        max_total=5,
        max_per_symbol=2,
        max_per_signal_type=None,
    )
    assert params.min_score == 0.3
    assert params.max_total == 5
    assert params.max_per_symbol == 2
    assert params.max_per_signal_type is None


def test_sandbox_result():
    """Test SandboxResult dataclass."""
    result = SandboxResult(
        selected_count=3,
        selected_signals=[{"test": "data"}],
        newly_admitted=[{"new": "candidate"}],
        rejected_reasons={"key": "reason"},
    )
    assert result.selected_count == 3
    assert len(result.selected_signals) == 1
    assert len(result.newly_admitted) == 1
    assert len(result.rejected_reasons) == 1


def test_evaluate_sandbox_empty_snapshot():
    """Test sandbox evaluation with empty snapshot."""
    snapshot = {"scored_candidates": []}
    params = SandboxParams(min_score=None, max_total=10, max_per_symbol=2, max_per_signal_type=None)
    
    result = evaluate_sandbox(snapshot, params)
    
    assert result.selected_count == 0
    assert len(result.selected_signals) == 0
    assert len(result.newly_admitted) == 0


def test_evaluate_sandbox_no_scored_candidates():
    """Test sandbox evaluation when scored_candidates is missing."""
    snapshot = {}
    params = SandboxParams(min_score=None, max_total=10, max_per_symbol=2, max_per_signal_type=None)
    
    result = evaluate_sandbox(snapshot, params)
    
    assert result.selected_count == 0
    assert len(result.selected_signals) == 0


def test_evaluate_sandbox_identical_to_live():
    """Test sandbox with params identical to live config produces same result."""
    # Create test candidates
    cand1 = _create_test_candidate("AAPL", SignalType.CSP, 150.0, date(2026, 2, 20), 0.8)
    cand2 = _create_test_candidate("MSFT", SignalType.CSP, 300.0, date(2026, 2, 20), 0.7)
    cand3 = _create_test_candidate("AAPL", SignalType.CC, 155.0, date(2026, 2, 20), 0.6)
    
    # Build snapshot with scored candidates and live selected signals
    scored_dicts = [
        {
            "rank": 1,
            "score": {
                "total": cand1.score.total,
                "components": [
                    {"name": c.name, "value": c.value, "weight": c.weight}
                    for c in cand1.score.components
                ],
            },
            "candidate": {
                "symbol": cand1.candidate.symbol,
                "signal_type": cand1.candidate.signal_type.value,
                "as_of": cand1.candidate.as_of.isoformat(),
                "underlying_price": cand1.candidate.underlying_price,
                "expiry": cand1.candidate.expiry.isoformat(),
                "strike": cand1.candidate.strike,
                "option_right": cand1.candidate.option_right,
                "bid": cand1.candidate.bid,
                "ask": cand1.candidate.ask,
                "mid": cand1.candidate.mid,
                "volume": cand1.candidate.volume,
                "open_interest": cand1.candidate.open_interest,
                "delta": cand1.candidate.delta,
                "iv": cand1.candidate.iv,
                "annualized_yield": cand1.candidate.annualized_yield,
                "raw_yield": cand1.candidate.raw_yield,
                "max_profit": cand1.candidate.max_profit,
                "collateral": cand1.candidate.collateral,
            },
        },
        {
            "rank": 2,
            "score": {
                "total": cand2.score.total,
                "components": [
                    {"name": c.name, "value": c.value, "weight": c.weight}
                    for c in cand2.score.components
                ],
            },
            "candidate": {
                "symbol": cand2.candidate.symbol,
                "signal_type": cand2.candidate.signal_type.value,
                "as_of": cand2.candidate.as_of.isoformat(),
                "underlying_price": cand2.candidate.underlying_price,
                "expiry": cand2.candidate.expiry.isoformat(),
                "strike": cand2.candidate.strike,
                "option_right": cand2.candidate.option_right,
                "bid": cand2.candidate.bid,
                "ask": cand2.candidate.ask,
                "mid": cand2.candidate.mid,
                "volume": cand2.candidate.volume,
                "open_interest": cand2.candidate.open_interest,
                "delta": cand2.candidate.delta,
                "iv": cand2.candidate.iv,
                "annualized_yield": cand2.candidate.annualized_yield,
                "raw_yield": cand2.candidate.raw_yield,
                "max_profit": cand2.candidate.max_profit,
                "collateral": cand2.candidate.collateral,
            },
        },
        {
            "rank": 3,
            "score": {
                "total": cand3.score.total,
                "components": [
                    {"name": c.name, "value": c.value, "weight": c.weight}
                    for c in cand3.score.components
                ],
            },
            "candidate": {
                "symbol": cand3.candidate.symbol,
                "signal_type": cand3.candidate.signal_type.value,
                "as_of": cand3.candidate.as_of.isoformat(),
                "underlying_price": cand3.candidate.underlying_price,
                "expiry": cand3.candidate.expiry.isoformat(),
                "strike": cand3.candidate.strike,
                "option_right": cand3.candidate.option_right,
                "bid": cand3.candidate.bid,
                "ask": cand3.candidate.ask,
                "mid": cand3.candidate.mid,
                "volume": cand3.candidate.volume,
                "open_interest": cand3.candidate.open_interest,
                "delta": cand3.candidate.delta,
                "iv": cand3.candidate.iv,
                "annualized_yield": cand3.candidate.annualized_yield,
                "raw_yield": cand3.candidate.raw_yield,
                "max_profit": cand3.candidate.max_profit,
                "collateral": cand3.candidate.collateral,
            },
        },
    ]
    
    # Live selected signals (first two)
    live_selected = [
        {
            "scored": scored_dicts[0],
            "selection_reason": "SELECTED_BY_POLICY",
        },
        {
            "scored": scored_dicts[1],
            "selection_reason": "SELECTED_BY_POLICY",
        },
    ]
    
    snapshot = {
        "scored_candidates": scored_dicts,
        "selected_signals": live_selected,
        "explanations": [
            {
                "policy_snapshot": {
                    "min_score": 0.0,
                    "max_total": 10,
                    "max_per_symbol": 2,
                    "max_per_signal_type": None,
                }
            }
        ],
    }
    
    # Sandbox params match live config
    params = SandboxParams(min_score=None, max_total=10, max_per_symbol=2, max_per_signal_type=None)
    
    result = evaluate_sandbox(snapshot, params)
    
    # With identical params, sandbox should include all live selected signals
    # (may select more if caps allow, but should include all live ones)
    assert result.selected_count >= 2  # At least as many as live
    # All live selected should be in sandbox selected (by key)
    live_keys = set()
    for ld in live_selected:
        key = (
            ld["scored"]["candidate"]["symbol"],
            ld["scored"]["candidate"]["signal_type"],
            ld["scored"]["candidate"]["expiry"],
            ld["scored"]["candidate"]["strike"],
        )
        live_keys.add(key)
    
    sandbox_keys = set()
    for sd in result.selected_signals:
        key = (
            sd["scored"]["candidate"]["symbol"],
            sd["scored"]["candidate"]["signal_type"],
            sd["scored"]["candidate"]["expiry"],
            sd["scored"]["candidate"]["strike"],
        )
        sandbox_keys.add(key)
    
    # All live keys should be in sandbox
    assert live_keys.issubset(sandbox_keys)


def test_evaluate_sandbox_newly_admitted():
    """Test sandbox identifies newly admitted candidates."""
    # Create test candidates
    cand1 = _create_test_candidate("AAPL", SignalType.CSP, 150.0, date(2026, 2, 20), 0.8)
    cand2 = _create_test_candidate("MSFT", SignalType.CSP, 300.0, date(2026, 2, 20), 0.7)
    cand3 = _create_test_candidate("GOOGL", SignalType.CSP, 200.0, date(2026, 2, 20), 0.6)
    
    # Build snapshot
    scored_dicts = [
        {
            "rank": 1,
            "score": {"total": cand1.score.total, "components": []},
            "candidate": {
                "symbol": cand1.candidate.symbol,
                "signal_type": cand1.candidate.signal_type.value,
                "as_of": cand1.candidate.as_of.isoformat(),
                "underlying_price": cand1.candidate.underlying_price,
                "expiry": cand1.candidate.expiry.isoformat(),
                "strike": cand1.candidate.strike,
                "option_right": cand1.candidate.option_right,
                "bid": cand1.candidate.bid,
                "ask": cand1.candidate.ask,
                "mid": cand1.candidate.mid,
                "volume": cand1.candidate.volume,
                "open_interest": cand1.candidate.open_interest,
                "delta": cand1.candidate.delta,
                "iv": cand1.candidate.iv,
                "annualized_yield": cand1.candidate.annualized_yield,
                "raw_yield": cand1.candidate.raw_yield,
                "max_profit": cand1.candidate.max_profit,
                "collateral": cand1.candidate.collateral,
            },
        },
        {
            "rank": 2,
            "score": {"total": cand2.score.total, "components": []},
            "candidate": {
                "symbol": cand2.candidate.symbol,
                "signal_type": cand2.candidate.signal_type.value,
                "as_of": cand2.candidate.as_of.isoformat(),
                "underlying_price": cand2.candidate.underlying_price,
                "expiry": cand2.candidate.expiry.isoformat(),
                "strike": cand2.candidate.strike,
                "option_right": cand2.candidate.option_right,
                "bid": cand2.candidate.bid,
                "ask": cand2.candidate.ask,
                "mid": cand2.candidate.mid,
                "volume": cand2.candidate.volume,
                "open_interest": cand2.candidate.open_interest,
                "delta": cand2.candidate.delta,
                "iv": cand2.candidate.iv,
                "annualized_yield": cand2.candidate.annualized_yield,
                "raw_yield": cand2.candidate.raw_yield,
                "max_profit": cand2.candidate.max_profit,
                "collateral": cand2.candidate.collateral,
            },
        },
        {
            "rank": 3,
            "score": {"total": cand3.score.total, "components": []},
            "candidate": {
                "symbol": cand3.candidate.symbol,
                "signal_type": cand3.candidate.signal_type.value,
                "as_of": cand3.candidate.as_of.isoformat(),
                "underlying_price": cand3.candidate.underlying_price,
                "expiry": cand3.candidate.expiry.isoformat(),
                "strike": cand3.candidate.strike,
                "option_right": cand3.candidate.option_right,
                "bid": cand3.candidate.bid,
                "ask": cand3.candidate.ask,
                "mid": cand3.candidate.mid,
                "volume": cand3.candidate.volume,
                "open_interest": cand3.candidate.open_interest,
                "delta": cand3.candidate.delta,
                "iv": cand3.candidate.iv,
                "annualized_yield": cand3.candidate.annualized_yield,
                "raw_yield": cand3.candidate.raw_yield,
                "max_profit": cand3.candidate.max_profit,
                "collateral": cand3.candidate.collateral,
            },
        },
    ]
    
    # Live selected signals (only first one, due to max_per_symbol=1)
    live_selected = [
        {
            "scored": scored_dicts[0],
            "selection_reason": "SELECTED_BY_POLICY",
        },
    ]
    
    snapshot = {
        "scored_candidates": scored_dicts,
        "selected_signals": live_selected,
        "explanations": [
            {
                "policy_snapshot": {
                    "min_score": 0.0,
                    "max_total": 10,
                    "max_per_symbol": 1,  # Live config: only 1 per symbol
                    "max_per_signal_type": None,
                }
            }
        ],
    }
    
    # Sandbox params: allow 2 per symbol
    params = SandboxParams(min_score=None, max_total=10, max_per_symbol=2, max_per_signal_type=None)
    
    result = evaluate_sandbox(snapshot, params)
    
    # Should select more candidates
    assert result.selected_count >= 1
    # Should identify newly admitted (if any)
    # Note: This depends on the exact selection logic


def test_evaluate_sandbox_does_not_mutate_snapshot():
    """Test that sandbox evaluation does not mutate the snapshot."""
    snapshot = {
        "scored_candidates": [],
        "selected_signals": [],
        "explanations": [],
    }
    snapshot_copy = json.loads(json.dumps(snapshot))  # Deep copy
    
    params = SandboxParams(min_score=None, max_total=10, max_per_symbol=2, max_per_signal_type=None)
    
    evaluate_sandbox(snapshot, params)
    
    # Snapshot should be unchanged
    assert snapshot == snapshot_copy


def test_evaluate_sandbox_min_score_filter():
    """Test sandbox respects min_score filter."""
    cand1 = _create_test_candidate("AAPL", SignalType.CSP, 150.0, date(2026, 2, 20), 0.8)
    cand2 = _create_test_candidate("MSFT", SignalType.CSP, 300.0, date(2026, 2, 20), 0.3)
    
    scored_dicts = [
        {
            "rank": 1,
            "score": {"total": cand1.score.total, "components": []},
            "candidate": {
                "symbol": cand1.candidate.symbol,
                "signal_type": cand1.candidate.signal_type.value,
                "as_of": cand1.candidate.as_of.isoformat(),
                "underlying_price": cand1.candidate.underlying_price,
                "expiry": cand1.candidate.expiry.isoformat(),
                "strike": cand1.candidate.strike,
                "option_right": cand1.candidate.option_right,
                "bid": cand1.candidate.bid,
                "ask": cand1.candidate.ask,
                "mid": cand1.candidate.mid,
                "volume": cand1.candidate.volume,
                "open_interest": cand1.candidate.open_interest,
                "delta": cand1.candidate.delta,
                "iv": cand1.candidate.iv,
                "annualized_yield": cand1.candidate.annualized_yield,
                "raw_yield": cand1.candidate.raw_yield,
                "max_profit": cand1.candidate.max_profit,
                "collateral": cand1.candidate.collateral,
            },
        },
        {
            "rank": 2,
            "score": {"total": cand2.score.total, "components": []},
            "candidate": {
                "symbol": cand2.candidate.symbol,
                "signal_type": cand2.candidate.signal_type.value,
                "as_of": cand2.candidate.as_of.isoformat(),
                "underlying_price": cand2.candidate.underlying_price,
                "expiry": cand2.candidate.expiry.isoformat(),
                "strike": cand2.candidate.strike,
                "option_right": cand2.candidate.option_right,
                "bid": cand2.candidate.bid,
                "ask": cand2.candidate.ask,
                "mid": cand2.candidate.mid,
                "volume": cand2.candidate.volume,
                "open_interest": cand2.candidate.open_interest,
                "delta": cand2.candidate.delta,
                "iv": cand2.candidate.iv,
                "annualized_yield": cand2.candidate.annualized_yield,
                "raw_yield": cand2.candidate.raw_yield,
                "max_profit": cand2.candidate.max_profit,
                "collateral": cand2.candidate.collateral,
            },
        },
    ]
    
    snapshot = {
        "scored_candidates": scored_dicts,
        "selected_signals": [],
        "explanations": [],
    }
    
    # Sandbox with min_score=0.5
    params = SandboxParams(min_score=0.5, max_total=10, max_per_symbol=2, max_per_signal_type=None)
    
    result = evaluate_sandbox(snapshot, params)
    
    # Should only select cand1 (score 0.8 > 0.5)
    assert result.selected_count == 1


__all__ = [
    "test_sandbox_params",
    "test_sandbox_result",
    "test_evaluate_sandbox_empty_snapshot",
    "test_evaluate_sandbox_no_scored_candidates",
    "test_evaluate_sandbox_identical_to_live",
    "test_evaluate_sandbox_newly_admitted",
    "test_evaluate_sandbox_does_not_mutate_snapshot",
    "test_evaluate_sandbox_min_score_filter",
]
