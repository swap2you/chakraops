# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for EOD strategy and strict Stage 1.

- Stage 1 strictly requires bid/ask/volume from delayed /datav2/strikes/options.
  If any are missing, Stage 1 BLOCKs; no OPRA waiver.
- When Stage 1 qualifies (all required present), Stage 2 liquidity can still come from
  OPRA pipeline; no waiver gate for stock fields.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock
import pytest

from app.core.eval.staged_evaluator import (
    evaluate_symbol_full,
    Stage1Result,
    Stage2Result,
    StockVerdict,
    FinalVerdict,
    EvaluationStage,
)
from app.core.options.orats_chain_pipeline import (
    EnrichedContract,
    OptionChainResult,
)
from app.core.orats.orats_opra import (
    OpraEnrichmentResult,
    OptionContract,
)


class TestEodLiquidityWaiver:
    """Tests for strict Stage 1 and Stage 2 liquidity (no stock-field waiver)."""

    def test_stage1_blocks_when_bid_ask_volume_missing_even_if_stage2_would_have_liquidity(self):
        """
        Stage 1 must BLOCK when bid/ask/volume are missing. No waiver when Stage 2 OPRA
        would have provided options liquidity.
        """
        # Stage 1 BLOCKed due to missing required bid/ask/volume
        mock_stage1 = Stage1Result(symbol="AAPL")
        mock_stage1.price = 180.0
        mock_stage1.bid = None
        mock_stage1.ask = None
        mock_stage1.volume = None
        mock_stage1.iv_rank = 45.0
        mock_stage1.data_completeness = 0.5
        mock_stage1.missing_fields = ["bid", "ask", "volume"]
        mock_stage1.stock_verdict = StockVerdict.BLOCKED
        mock_stage1.stock_verdict_reason = "DATA_INCOMPLETE: required missing (bid, ask, volume)"
        mock_stage1.stage1_score = 50
        mock_stage1.regime = "NEUTRAL"
        mock_stage1.risk_posture = "MODERATE"

        with patch("app.core.eval.staged_evaluator.evaluate_stage1") as mock_eval_stage1:
            mock_eval_stage1.return_value = mock_stage1

            result = evaluate_symbol_full("AAPL")

        # Must be BLOCKED; we never run Stage 2 when Stage 1 blocks
        assert result.verdict == "BLOCKED"
        assert result.final_verdict == FinalVerdict.BLOCKED
        assert "bid" in result.missing_fields or "ask" in result.missing_fields or "volume" in result.missing_fields
        # No EOD Strategy Data Waiver gate (waiver removed)
        waiver_gate = next(
            (g for g in result.gates if g.get("name") == "EOD Strategy Data Waiver"),
            None,
        )
        assert waiver_gate is None

    def test_missing_stock_price_still_blocks(self):
        """
        Given:
            - Stock price is MISSING (fatal)
            - Valid ORATS option chain
        
        Expect:
            - Symbol is BLOCKED
            - DATA_INCOMPLETE_FATAL
        """
        mock_stage1 = Stage1Result(symbol="AAPL")
        mock_stage1.price = None  # Missing - fatal!
        mock_stage1.stock_verdict = StockVerdict.BLOCKED
        mock_stage1.stock_verdict_reason = "DATA_INCOMPLETE_FATAL: No price data"
        
        with patch("app.core.eval.staged_evaluator.evaluate_stage1") as mock_eval_stage1:
            mock_eval_stage1.return_value = mock_stage1
            
            result = evaluate_symbol_full("AAPL")
            
            # Should be blocked due to missing price
            assert result.verdict == "BLOCKED" or "DATA_INCOMPLETE" in result.primary_reason
            assert result.final_verdict != FinalVerdict.ELIGIBLE

    def test_no_option_liquidity_still_holds(self):
        """
        Given Stage 1 qualified (all required fields present) and Stage 2 has no
        option liquidity (and enhancement does not add any), expect HOLD. No waiver gate.
        """
        mock_stage1 = Stage1Result(symbol="AAPL")
        mock_stage1.price = 180.0
        mock_stage1.bid = 179.9
        mock_stage1.ask = 180.1
        mock_stage1.volume = 1_000_000
        mock_stage1.data_completeness = 1.0
        mock_stage1.missing_fields = []
        mock_stage1.stock_verdict = StockVerdict.QUALIFIED
        mock_stage1.stage1_score = 70
        mock_stage1.regime = "NEUTRAL"
        mock_stage1.risk_posture = "MODERATE"

        mock_stage2 = Stage2Result(symbol="AAPL")
        mock_stage2.liquidity_ok = False
        mock_stage2.liquidity_reason = "No contracts meeting criteria"
        mock_stage2.chain_missing_fields = []
        mock_stage2.expirations_available = 0

        def no_enhance(_sym, s2):
            return s2  # Return stage2 unchanged so liquidity_ok stays False

        with patch("app.core.eval.staged_evaluator.evaluate_stage1") as mock_eval_stage1, \
             patch("app.core.eval.staged_evaluator.evaluate_stage2") as mock_eval_stage2, \
             patch("app.core.eval.staged_evaluator._enhance_liquidity_with_pipeline", side_effect=no_enhance):
            mock_eval_stage1.return_value = mock_stage1
            mock_eval_stage2.return_value = mock_stage2

            result = evaluate_symbol_full("AAPL")

        assert result.liquidity_ok is False
        assert result.verdict == "HOLD"
        waiver_gate = next(
            (g for g in result.gates if g.get("name") == "EOD Strategy Data Waiver"),
            None,
        )
        assert waiver_gate is None, "No EOD waiver gate (waiver removed)"


class TestEnhancementLogging:
    """Tests to verify enhancement logging is working."""

    def test_enhancement_logs_are_generated(self, caplog):
        """Verify that enhancement attempt generates logs."""
        import logging
        caplog.set_level(logging.INFO)
        
        # Mock empty chain from pipeline
        mock_chain = OptionChainResult(
            symbol="SPY",
            contracts=[],
            error="Test error",
        )
        
        with patch("app.core.options.orats_chain_pipeline.fetch_option_chain") as mock_fetch:
            mock_fetch.return_value = mock_chain
            
            from app.core.eval.staged_evaluator import _enhance_liquidity_with_pipeline, Stage2Result
            
            stage2 = Stage2Result(symbol="SPY")
            stage2.liquidity_ok = False
            stage2.liquidity_reason = "No contracts"
            
            _enhance_liquidity_with_pipeline("SPY", stage2)
            
            # Check that enhancement logging occurred
            log_messages = [r.message for r in caplog.records]
            assert any("STAGE2_ENHANCE" in msg for msg in log_messages), \
                f"Expected STAGE2_ENHANCE log, got: {log_messages}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
