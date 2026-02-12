# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for confidence gating (Phase 2.4): min_confidence_threshold excludes low-confidence candidates."""

from __future__ import annotations

from datetime import date, datetime

from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import ScoredSignalCandidate, SignalScore
from app.signals.selection import SelectionConfig, select_signals


def _make_scored(
    symbol: str,
    signal_type: SignalType,
    score_total: float,
    rank: int,
    dte: int = 30,
    underlying_price: float = 100.0,
) -> ScoredSignalCandidate:
    """Build a minimal scored candidate; as_of and expiry set so calc_dte yields dte."""
    from datetime import timedelta
    as_of = datetime(2026, 1, 22, 10, 0, 0)
    expiry = (as_of.date() + timedelta(days=dte)) if dte is not None else date(2026, 2, 20)
    cand = SignalCandidate(
        symbol=symbol,
        signal_type=signal_type,
        as_of=as_of,
        underlying_price=underlying_price,
        expiry=expiry,
        strike=100.0,
        option_right="PUT" if signal_type == SignalType.CSP else "CALL",
        bid=1.0,
        ask=1.1,
        mid=None,
        volume=1000,
        open_interest=1000,
        delta=None,
        prob_otm=None,
        iv_rank=None,
        iv=None,
        annualized_yield=None,
        raw_yield=None,
        max_profit=None,
        collateral=None,
    )
    return ScoredSignalCandidate(
        candidate=cand,
        score=SignalScore(total=score_total, components=[]),
        rank=rank,
    )


class TestConfidenceGateExcludesBelowThreshold:
    """Candidates below min_confidence_threshold are excluded and get confidence_below_threshold."""

    def test_below_threshold_excluded(self):
        """With system_health DEGRADED, confidence is 30; threshold 40 excludes candidate."""
        scored = [
            _make_scored("AAPL", SignalType.CSP, score_total=0.9, rank=1),
        ]
        cfg = SelectionConfig(
            max_total=10,
            max_per_symbol=2,
            max_per_signal_type=None,
            min_score=0.0,
            min_confidence_threshold=40,
        )
        context = {"system_health_status": "DEGRADED"}  # score 50 - 20 = 30
        selected, exclusions = select_signals(scored, cfg, confidence_context=context)
        assert len(selected) == 0
        assert len(exclusions) == 1
        assert exclusions[0].code == "confidence_below_threshold"
        assert exclusions[0].data.get("symbol") == "AAPL"
        assert exclusions[0].data.get("confidence_score") == 30
        assert exclusions[0].data.get("min_confidence_threshold") == 40

    def test_halt_excluded(self):
        """With system_health HALT, confidence is 10; threshold 40 excludes candidate."""
        scored = [
            _make_scored("MSFT", SignalType.CSP, score_total=0.95, rank=1),
        ]
        cfg = SelectionConfig(
            max_total=10,
            max_per_symbol=2,
            max_per_signal_type=None,
            min_score=0.0,
            min_confidence_threshold=40,
        )
        context = {"system_health_status": "HALT"}  # score 50 - 40 = 10
        selected, exclusions = select_signals(scored, cfg, confidence_context=context)
        assert len(selected) == 0
        assert len(exclusions) == 1
        assert exclusions[0].code == "confidence_below_threshold"
        assert exclusions[0].data.get("confidence_score") == 10


class TestConfidenceGatePassesAtOrAboveThreshold:
    """Candidates at or above min_confidence_threshold are considered."""

    def test_at_threshold_considered(self):
        """Confidence 40 with threshold 40 is not excluded."""
        scored = [
            _make_scored("AAPL", SignalType.CSP, score_total=0.9, rank=1),
        ]
        cfg = SelectionConfig(
            max_total=10,
            max_per_symbol=2,
            max_per_signal_type=None,
            min_score=0.0,
            min_confidence_threshold=40,
        )
        # Default context: regime_confidence=50, no penalties -> score 50 >= 40
        selected, exclusions = select_signals(scored, cfg, confidence_context={})
        assert len(selected) == 1
        assert len(exclusions) == 0
        assert selected[0].scored.candidate.symbol == "AAPL"

    def test_above_threshold_considered(self):
        """Confidence above threshold (e.g. 50) is selected."""
        scored = [
            _make_scored("AAPL", SignalType.CSP, score_total=0.9, rank=1),
            _make_scored("MSFT", SignalType.CSP, score_total=0.8, rank=2),
        ]
        cfg = SelectionConfig(
            max_total=10,
            max_per_symbol=2,
            max_per_signal_type=None,
            min_score=0.0,
            min_confidence_threshold=40,
        )
        selected, exclusions = select_signals(scored, cfg, confidence_context={})
        assert len(selected) == 2
        assert len(exclusions) == 0

    def test_no_threshold_no_confidence_gating(self):
        """When min_confidence_threshold is None, no confidence exclusions."""
        scored = [
            _make_scored("AAPL", SignalType.CSP, score_total=0.9, rank=1),
        ]
        cfg = SelectionConfig(
            max_total=10,
            max_per_symbol=2,
            max_per_signal_type=None,
            min_score=0.0,
            min_confidence_threshold=None,
        )
        context = {"system_health_status": "HALT"}  # would be 10 if we gated
        selected, exclusions = select_signals(scored, cfg, confidence_context=context)
        assert len(selected) == 1
        assert len(exclusions) == 0


class TestConfidenceGateExclusionReasons:
    """Exclusion reasons are properly set for decision snapshots."""

    def test_exclusion_reason_has_code_message_data(self):
        """Excluded candidate has code, message, and data (symbol, score, threshold)."""
        scored = [
            _make_scored("XYZ", SignalType.CC, score_total=0.85, rank=1),
        ]
        cfg = SelectionConfig(
            max_total=10,
            max_per_symbol=2,
            max_per_signal_type=None,
            min_score=0.0,
            min_confidence_threshold=50,
        )
        context = {"system_health_status": "DEGRADED"}  # 30 < 50
        selected, exclusions = select_signals(scored, cfg, confidence_context=context)
        assert len(exclusions) == 1
        r = exclusions[0]
        assert r.code == "confidence_below_threshold"
        assert "below threshold" in r.message
        assert "XYZ" in r.message
        assert r.data.get("symbol") == "XYZ"
        assert r.data.get("signal_type") == "CC"
        assert r.data.get("confidence_score") == 30
        assert r.data.get("min_confidence_threshold") == 50
