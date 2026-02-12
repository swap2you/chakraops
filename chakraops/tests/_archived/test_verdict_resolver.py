# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for verdict resolution with proper DATA_INCOMPLETE classification.

Covers:
1. CLOSED market + missing bid/ask → not fatal (DATA_INCOMPLETE_INTRADAY)
2. Verdict precedence ordering
3. DATA_INCOMPLETE_FATAL vs INTRADAY classification
4. Market status impact on verdict
"""

from __future__ import annotations

import pytest

from app.core.eval.verdict_resolver import (
    DataIncompleteType,
    MarketStatus,
    VerdictResolution,
    classify_data_incompleteness,
    resolve_final_verdict,
    FATAL_MISSING_FIELDS,
    INTRADAY_ONLY_FIELDS,
)


class TestClassifyDataIncompleteness:
    """Tests for DATA_INCOMPLETE classification based on missing fields and market status."""

    def test_no_missing_fields_returns_none(self) -> None:
        """Complete data returns NONE type."""
        data_type, reason = classify_data_incompleteness(
            missing_fields=[],
            market_status=MarketStatus.OPEN,
            has_options_chain=True,
        )
        assert data_type == DataIncompleteType.NONE
        assert reason == ""

    def test_missing_price_is_fatal(self) -> None:
        """Missing price is always FATAL regardless of market status."""
        for status in [MarketStatus.OPEN, MarketStatus.CLOSED, MarketStatus.UNKNOWN]:
            data_type, reason = classify_data_incompleteness(
                missing_fields=["price"],
                market_status=status,
                has_options_chain=True,
            )
            assert data_type == DataIncompleteType.FATAL
            assert "FATAL" in reason
            assert "price" in reason.lower()

    def test_no_options_chain_is_fatal(self) -> None:
        """No options chain is always FATAL."""
        data_type, reason = classify_data_incompleteness(
            missing_fields=[],
            market_status=MarketStatus.OPEN,
            has_options_chain=False,
        )
        assert data_type == DataIncompleteType.FATAL
        assert "no options chain" in reason.lower()

    def test_missing_bid_ask_open_market_is_intraday(self) -> None:
        """Missing bid/ask during OPEN market is INTRADAY (not fatal)."""
        data_type, reason = classify_data_incompleteness(
            missing_fields=["bid", "ask"],
            market_status=MarketStatus.OPEN,
            has_options_chain=True,
        )
        assert data_type == DataIncompleteType.INTRADAY
        assert "INTRADAY" in reason
        assert "bid" in reason.lower()

    def test_missing_bid_ask_closed_market_is_intraday_non_fatal(self) -> None:
        """Missing bid/ask during CLOSED market is INTRADAY and explicitly marked non-fatal."""
        data_type, reason = classify_data_incompleteness(
            missing_fields=["bid", "ask", "volume"],
            market_status=MarketStatus.CLOSED,
            has_options_chain=True,
        )
        assert data_type == DataIncompleteType.INTRADAY
        assert "INTRADAY" in reason
        assert "non-fatal" in reason.lower() or "CLOSED" in reason

    def test_missing_volume_closed_market_is_intraday(self) -> None:
        """Missing volume during CLOSED market is INTRADAY."""
        data_type, reason = classify_data_incompleteness(
            missing_fields=["volume"],
            market_status=MarketStatus.CLOSED,
            has_options_chain=True,
        )
        assert data_type == DataIncompleteType.INTRADAY
        assert "CLOSED" in reason or "non-fatal" in reason.lower()


class TestVerdictPrecedence:
    """Tests for verdict precedence ordering."""

    def test_position_blocked_highest_priority(self) -> None:
        """Position blocking takes highest priority over everything."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            position_blocked=True,
            position_reason="CSP already open",
            missing_fields=["bid"],
            market_status=MarketStatus.CLOSED,
            market_regime="RISK_OFF",  # Would normally force HOLD
        )
        assert resolution.verdict == "BLOCKED"
        assert resolution.reason_code == "POSITION_BLOCKED"
        assert resolution.was_downgraded is True

    def test_exposure_blocked_high_priority(self) -> None:
        """Exposure blocking takes high priority."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            exposure_blocked=True,
            exposure_reason="Max positions reached",
            market_regime="RISK_ON",
        )
        assert resolution.verdict == "BLOCKED"
        assert resolution.reason_code == "EXPOSURE_BLOCKED"

    def test_fatal_data_incomplete_blocks_eligible(self) -> None:
        """DATA_INCOMPLETE_FATAL forces HOLD even for ELIGIBLE."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            missing_fields=["price"],  # FATAL
            has_options_chain=True,
            market_status=MarketStatus.OPEN,
            market_regime="RISK_ON",
        )
        assert resolution.verdict == "HOLD"
        assert resolution.reason_code == "DATA_INCOMPLETE_FATAL"
        assert resolution.data_incomplete_type == DataIncompleteType.FATAL

    def test_risk_off_forces_hold(self) -> None:
        """RISK_OFF regime forces HOLD."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            missing_fields=[],
            market_status=MarketStatus.OPEN,
            market_regime="RISK_OFF",
        )
        assert resolution.verdict == "HOLD"
        assert resolution.reason_code == "REGIME_RISK_OFF"
        assert resolution.was_downgraded is True

    def test_eligible_preserved_when_no_blockers(self) -> None:
        """ELIGIBLE stays ELIGIBLE when no blockers apply."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            missing_fields=[],
            market_status=MarketStatus.OPEN,
            market_regime="RISK_ON",
        )
        assert resolution.verdict == "ELIGIBLE"
        assert resolution.reason_code == "ELIGIBLE"
        assert resolution.was_downgraded is False

    def test_intraday_incomplete_does_not_block_when_closed(self) -> None:
        """DATA_INCOMPLETE_INTRADAY does NOT block ELIGIBLE when market CLOSED."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            missing_fields=["bid", "ask", "volume"],  # All intraday fields
            has_options_chain=True,
            market_status=MarketStatus.CLOSED,
            market_regime="RISK_ON",
        )
        assert resolution.verdict == "ELIGIBLE"
        assert resolution.data_incomplete_type == DataIncompleteType.INTRADAY
        # Should note market closed in reason
        assert "closed" in resolution.reason.lower()


class TestPrecedenceOrder:
    """Tests to verify exact precedence order: BLOCKED > FATAL > HOLD > ELIGIBLE."""

    def test_position_beats_fatal_incomplete(self) -> None:
        """Position blocking beats DATA_INCOMPLETE_FATAL."""
        resolution = resolve_final_verdict(
            current_verdict="HOLD",
            current_reason="Data incomplete",
            score=50,
            position_blocked=True,
            position_reason="Position open",
            missing_fields=["price"],  # Would be FATAL
            market_status=MarketStatus.OPEN,
        )
        assert resolution.verdict == "BLOCKED"
        assert resolution.reason_code == "POSITION_BLOCKED"

    def test_fatal_beats_risk_off(self) -> None:
        """DATA_INCOMPLETE_FATAL is checked before regime."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            missing_fields=["price"],  # FATAL
            market_status=MarketStatus.OPEN,
            market_regime="RISK_OFF",
        )
        # Position not blocked, so we check DATA_INCOMPLETE_FATAL first
        # Actually, BLOCKED (position) > FATAL > HOLD (regime)
        # Since position not blocked, should be FATAL
        assert resolution.verdict == "HOLD"
        assert resolution.reason_code == "DATA_INCOMPLETE_FATAL"

    def test_risk_off_beats_eligible(self) -> None:
        """RISK_OFF regime beats ELIGIBLE verdict."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Perfect setup",
            score=95,
            missing_fields=[],
            market_status=MarketStatus.OPEN,
            market_regime="RISK_OFF",
        )
        assert resolution.verdict == "HOLD"
        assert resolution.reason_code == "REGIME_RISK_OFF"


class TestMarketStatusImpact:
    """Tests for market status impact on DATA_INCOMPLETE handling."""

    def test_closed_market_tolerates_missing_bid_ask(self) -> None:
        """CLOSED market tolerates missing bid/ask (EOD strategy)."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="EOD evaluation",
            score=80,
            missing_fields=["bid", "ask", "bidSize", "askSize"],
            has_options_chain=True,
            market_status=MarketStatus.CLOSED,
            market_regime="RISK_ON",
        )
        # Should remain ELIGIBLE because bid/ask are intraday-only fields
        assert resolution.verdict == "ELIGIBLE"
        assert resolution.data_incomplete_type == DataIncompleteType.INTRADAY

    def test_open_market_still_allows_intraday_incomplete(self) -> None:
        """OPEN market with missing bid/ask is INTRADAY but not fatal."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Live evaluation",
            score=80,
            missing_fields=["bid", "ask"],
            has_options_chain=True,
            market_status=MarketStatus.OPEN,
            market_regime="RISK_ON",
        )
        # INTRADAY incomplete during OPEN is concerning but not fatal
        assert resolution.verdict == "ELIGIBLE"
        assert resolution.data_incomplete_type == DataIncompleteType.INTRADAY

    def test_unknown_market_status_conservative(self) -> None:
        """UNKNOWN market status is treated conservatively."""
        data_type, _ = classify_data_incompleteness(
            missing_fields=["bid", "ask"],
            market_status=MarketStatus.UNKNOWN,
            has_options_chain=True,
        )
        assert data_type == DataIncompleteType.INTRADAY


class TestDowngradeTracking:
    """Tests for verdict downgrade tracking."""

    def test_downgrade_from_eligible_to_hold_tracked(self) -> None:
        """Downgrade from ELIGIBLE to HOLD is tracked."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            market_regime="RISK_OFF",
        )
        assert resolution.was_downgraded is True
        assert resolution.downgrade_reason is not None
        assert "RISK_OFF" in (resolution.downgrade_reason or "")

    def test_no_downgrade_when_already_hold(self) -> None:
        """No downgrade tracked when already HOLD."""
        resolution = resolve_final_verdict(
            current_verdict="HOLD",
            current_reason="Already on hold",
            score=45,
            market_regime="RISK_ON",
        )
        assert resolution.was_downgraded is False


class TestStrategyOutcomeVsDataFailure:
    """Phase 8C: Strategy outcomes must never appear as data failures."""

    def test_position_blocked_reason_not_data_incomplete(self) -> None:
        """When BLOCKED by position, reason and reason_code are position-related, not DATA_INCOMPLETE."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            position_blocked=True,
            position_reason="POSITION_ALREADY_OPEN",
            missing_fields=["bid"],  # would be data issue if we reached that branch
            has_options_chain=True,
            market_status=MarketStatus.OPEN,
        )
        assert resolution.reason_code == "POSITION_BLOCKED"
        assert not resolution.reason.strip().upper().startswith("DATA_INCOMPLETE")
        assert "POSITION" in resolution.reason.upper() or "ALREADY" in resolution.reason.upper()

    def test_regime_hold_reason_not_data_incomplete(self) -> None:
        """When HOLD due to regime, reason_code is REGIME_RISK_OFF, not DATA_INCOMPLETE."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            missing_fields=[],
            market_regime="RISK_OFF",
        )
        assert resolution.reason_code == "REGIME_RISK_OFF"
        assert resolution.reason_code != "DATA_INCOMPLETE_FATAL"
        assert "REGIME" in resolution.reason.upper() or "RISK" in resolution.reason.upper()

    def test_exposure_blocked_reason_not_data_incomplete(self) -> None:
        """When BLOCKED by exposure, reason_code is EXPOSURE_BLOCKED."""
        resolution = resolve_final_verdict(
            current_verdict="ELIGIBLE",
            current_reason="Chain selected",
            score=85,
            exposure_blocked=True,
            exposure_reason="Max sector exposure",
            missing_fields=[],
        )
        assert resolution.reason_code == "EXPOSURE_BLOCKED"
        assert not resolution.reason.strip().upper().startswith("DATA_INCOMPLETE")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
