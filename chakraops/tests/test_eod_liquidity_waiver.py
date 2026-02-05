# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for EOD strategy liquidity waiver.

Validates that symbols can progress past HOLD when:
- Stock bid/ask/volume are missing
- But valid ORATS option chain liquidity exists (via two-step pipeline)

This is correct behavior for EOD options strategies (Wheel/CSP/CC).
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
    """Tests for EOD strategy liquidity waiver logic."""

    def test_missing_stock_liquidity_but_valid_options_progresses_past_hold(self):
        """
        Given:
            - Stock price exists
            - Stock bid/ask/volume are MISSING
            - Valid ORATS OPRA enrichment (strikes/options) returns valid liquidity
        
        Expect:
            - Symbol progresses past HOLD
            - Stock bid/ask/volume are waived
            - Verdict is ELIGIBLE (not HOLD)
        """
        # Mock stage 1: Stock price exists, but bid/ask/volume missing
        mock_stage1 = Stage1Result(symbol="AAPL")
        mock_stage1.price = 180.0
        mock_stage1.bid = None  # Missing
        mock_stage1.ask = None  # Missing
        mock_stage1.volume = None  # Missing
        mock_stage1.iv_rank = 45.0
        mock_stage1.data_completeness = 0.5
        mock_stage1.missing_fields = ["bid", "ask", "volume"]
        mock_stage1.stock_verdict = StockVerdict.QUALIFIED
        mock_stage1.stock_verdict_reason = "Stock qualified with missing intraday fields"
        mock_stage1.stage1_score = 60
        mock_stage1.regime = "NEUTRAL"
        mock_stage1.risk_posture = "MODERATE"
        
        # OPRA enrichment result with valid liquidity (used by _enhance_liquidity_with_pipeline)
        valid_put = OptionContract(
            symbol="AAPL",
            option_symbol="AAPL260320P00175000",
            expir_date="2026-03-20",
            strike=175.0,
            option_type="PUT",
            dte=31,
            bid_price=4.40,
            ask_price=4.50,
            volume=100,
            open_interest=539,
            delta=-0.32,
        )
        mock_opra_result = OpraEnrichmentResult(
            symbol="AAPL",
            underlying=None,  # Stock bid/ask missing - waiver applies
            options=[valid_put] * 5,  # 5 valid puts so gate passes
            strikes_rows=20,
            opra_symbols_built=10,
            option_rows_returned=10,
            underlying_row_returned=False,
            error=None,
        )
        
        with patch("app.core.eval.staged_evaluator.evaluate_stage1") as mock_eval_stage1, \
             patch("app.core.eval.staged_evaluator.evaluate_stage2") as mock_eval_stage2, \
             patch("app.core.orats.orats_opra.fetch_opra_enrichment") as mock_fetch_opra:
            
            mock_eval_stage1.return_value = mock_stage1
            
            # Stage 2 initially fails (e.g. live chain had no OPRA data)
            mock_stage2 = Stage2Result(symbol="AAPL")
            mock_stage2.expirations_available = 5
            mock_stage2.expirations_evaluated = 3
            mock_stage2.contracts_evaluated = 100
            mock_stage2.liquidity_ok = False
            mock_stage2.liquidity_reason = "No contracts meeting criteria"
            mock_stage2.chain_missing_fields = ["open_interest", "bid", "ask"]
            mock_eval_stage2.return_value = mock_stage2
            
            mock_fetch_opra.return_value = mock_opra_result
            
            result = evaluate_symbol_full("AAPL")
            
            # OPRA enrichment (two-step pipeline) was invoked
            mock_fetch_opra.assert_called_once()
            
            assert result.liquidity_ok == True, "liquidity_ok should be True after OPRA enhancement"
            
            waiver_gate = next(
                (g for g in result.gates if g.get("name") == "EOD Strategy Data Waiver"),
                None
            )
            assert waiver_gate is not None, "EOD Strategy Data Waiver gate should exist"
            assert waiver_gate["status"] == "WAIVED"
            assert "DERIVED_FROM_OPRA" in waiver_gate["reason"]
            
            assert result.verdict == "ELIGIBLE", f"Expected ELIGIBLE but got {result.verdict}"
            assert result.final_verdict == FinalVerdict.ELIGIBLE
            
            for field in ["bid", "ask", "volume"]:
                assert field not in result.missing_fields, f"{field} should be waived"

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
        Given:
            - Stock price exists, bid/ask/volume missing
            - OPRA enrichment returns no valid liquidity (error or zero valid contracts)
        
        Expect:
            - Symbol stays at HOLD
            - No waiver applied
        """
        mock_stage1 = Stage1Result(symbol="AAPL")
        mock_stage1.price = 180.0
        mock_stage1.bid = None
        mock_stage1.ask = None
        mock_stage1.volume = None
        mock_stage1.data_completeness = 0.5
        mock_stage1.missing_fields = ["bid", "ask", "volume"]
        mock_stage1.stock_verdict = StockVerdict.QUALIFIED
        mock_stage1.stage1_score = 50
        mock_stage1.regime = "NEUTRAL"
        mock_stage1.risk_posture = "MODERATE"
        
        # OPRA enrichment returns no valid liquidity (fails gate)
        mock_opra_result = OpraEnrichmentResult(
            symbol="AAPL",
            underlying=None,
            options=[],  # No options with valid liquidity
            strikes_rows=0,
            opra_symbols_built=0,
            option_rows_returned=0,
            underlying_row_returned=False,
            error="No strikes data returned",
        )
        
        with patch("app.core.eval.staged_evaluator.evaluate_stage1") as mock_eval_stage1, \
             patch("app.core.eval.staged_evaluator.evaluate_stage2") as mock_eval_stage2, \
             patch("app.core.orats.orats_opra.fetch_opra_enrichment") as mock_fetch_opra:
            
            mock_eval_stage1.return_value = mock_stage1
            
            mock_stage2 = Stage2Result(symbol="AAPL")
            mock_stage2.liquidity_ok = False
            mock_stage2.liquidity_reason = "No contracts meeting criteria"
            mock_stage2.chain_missing_fields = []
            mock_stage2.expirations_available = 0
            mock_eval_stage2.return_value = mock_stage2
            
            mock_fetch_opra.return_value = mock_opra_result
            
            result = evaluate_symbol_full("AAPL")
            
            # Should remain HOLD - OPRA did not provide valid liquidity
            assert result.liquidity_ok == False
            assert result.verdict == "HOLD"
            
            waiver_gate = next(
                (g for g in result.gates if g.get("name") == "EOD Strategy Data Waiver"),
                None
            )
            assert waiver_gate is None, "No waiver should be applied without option liquidity"


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
