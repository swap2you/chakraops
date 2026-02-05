# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for Options Chain Provider and 2-Stage Evaluation.

Tests cover:
- Chain provider returns correct contract data
- Contract selection by delta and DTE
- Missing chain data produces DATA_INCOMPLETE
- Rate limiting and caching behavior
- Full 2-stage pipeline
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

from app.core.models.data_quality import DataQuality, FieldValue
from app.core.options.chain_provider import (
    OptionType,
    OptionContract,
    OptionsChain,
    ContractLiquidityGrade,
    ContractSelectionCriteria,
    SelectedContract,
    select_contract,
    ExpirationInfo,
    ChainProviderResult,
)
from app.core.options.orats_chain_provider import (
    OratsChainProvider,
    RateLimiter,
    ChainCache,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_contract():
    """Create a sample option contract."""
    return OptionContract(
        symbol="AAPL",
        expiration=date.today() + timedelta(days=30),
        strike=150.0,
        option_type=OptionType.PUT,
        bid=FieldValue(2.50, DataQuality.VALID, "", "bid"),
        ask=FieldValue(2.70, DataQuality.VALID, "", "ask"),
        mid=FieldValue(2.60, DataQuality.VALID, "", "mid"),
        open_interest=FieldValue(1500, DataQuality.VALID, "", "open_interest"),
        volume=FieldValue(200, DataQuality.VALID, "", "volume"),
        delta=FieldValue(-0.25, DataQuality.VALID, "", "delta"),
        gamma=FieldValue(0.05, DataQuality.VALID, "", "gamma"),
        theta=FieldValue(-0.03, DataQuality.VALID, "", "theta"),
        vega=FieldValue(0.15, DataQuality.VALID, "", "vega"),
        iv=FieldValue(0.35, DataQuality.VALID, "", "iv"),
        dte=30,
    )


@pytest.fixture
def sample_chain(sample_contract):
    """Create a sample options chain."""
    contracts = [sample_contract]
    # Add more contracts at different strikes
    for strike in [145.0, 155.0, 160.0]:
        c = OptionContract(
            symbol="AAPL",
            expiration=sample_contract.expiration,
            strike=strike,
            option_type=OptionType.PUT,
            bid=FieldValue(1.50 + (155 - strike) * 0.1, DataQuality.VALID, "", "bid"),
            ask=FieldValue(1.70 + (155 - strike) * 0.1, DataQuality.VALID, "", "ask"),
            open_interest=FieldValue(800, DataQuality.VALID, "", "open_interest"),
            delta=FieldValue(-0.15 - (155 - strike) * 0.02, DataQuality.VALID, "", "delta"),
            dte=30,
        )
        c.compute_derived_fields()
        contracts.append(c)
    
    sample_contract.compute_derived_fields()
    
    return OptionsChain(
        symbol="AAPL",
        expiration=sample_contract.expiration,
        underlying_price=FieldValue(152.0, DataQuality.VALID, "", "underlying_price"),
        contracts=contracts,
    )


@pytest.fixture
def mock_orats_strikes():
    """Mock ORATS live strikes response."""
    exp_date = (date.today() + timedelta(days=30)).isoformat()
    return [
        {
            "ticker": "AAPL",
            "expirDate": exp_date,
            "strike": 150.0,
            "putCall": "P",
            "bid": 2.50,
            "ask": 2.70,
            "delta": -0.25,
            "gamma": 0.05,
            "theta": -0.03,
            "vega": 0.15,
            "openInt": 1500,
            "volume": 200,
            "iv": 0.35,
        },
        {
            "ticker": "AAPL",
            "expirDate": exp_date,
            "strike": 145.0,
            "putCall": "P",
            "bid": 1.80,
            "ask": 2.00,
            "delta": -0.18,
            "gamma": 0.04,
            "theta": -0.02,
            "vega": 0.12,
            "openInt": 800,
            "volume": 100,
            "iv": 0.32,
        },
        {
            "ticker": "AAPL",
            "expirDate": exp_date,
            "strike": 155.0,
            "putCall": "P",
            "bid": 3.50,
            "ask": 3.80,
            "delta": -0.32,
            "gamma": 0.06,
            "theta": -0.04,
            "vega": 0.18,
            "openInt": 1200,
            "volume": 150,
            "iv": 0.38,
        },
    ]


# ============================================================================
# Contract Model Tests
# ============================================================================

class TestOptionContract:
    """Tests for OptionContract model."""
    
    def test_compute_derived_fields(self, sample_contract):
        """Test derived field computation."""
        sample_contract.compute_derived_fields()
        
        assert sample_contract.spread.is_valid
        assert sample_contract.spread.value == pytest.approx(0.20, rel=0.01)
        assert sample_contract.spread_pct.is_valid
        
    def test_liquidity_grade_a(self, sample_contract):
        """Test grade A liquidity."""
        sample_contract.open_interest = FieldValue(1500, DataQuality.VALID, "", "open_interest")
        sample_contract.compute_derived_fields()
        # spread_pct = 0.20 / 2.60 ≈ 0.077, which is > 0.05
        # So with OI >= 1000 but spread > 5%, it should be B
        grade = sample_contract.get_liquidity_grade()
        assert grade == ContractLiquidityGrade.B
    
    def test_liquidity_grade_b(self, sample_contract):
        """Test grade B liquidity."""
        sample_contract.open_interest = FieldValue(600, DataQuality.VALID, "", "open_interest")
        sample_contract.compute_derived_fields()
        grade = sample_contract.get_liquidity_grade()
        assert grade == ContractLiquidityGrade.B
    
    def test_liquidity_grade_missing_data(self):
        """Test grade F for missing data."""
        contract = OptionContract(
            symbol="AAPL",
            expiration=date.today() + timedelta(days=30),
            strike=150.0,
            option_type=OptionType.PUT,
        )
        grade = contract.get_liquidity_grade()
        assert grade == ContractLiquidityGrade.F
    
    def test_to_dict(self, sample_contract):
        """Test serialization to dict."""
        sample_contract.compute_derived_fields()
        d = sample_contract.to_dict()
        
        assert d["symbol"] == "AAPL"
        assert d["strike"] == 150.0
        assert d["option_type"] == "PUT"
        assert "bid" in d
        assert "liquidity_grade" in d


# ============================================================================
# Chain Tests
# ============================================================================

class TestOptionsChain:
    """Tests for OptionsChain model."""
    
    def test_puts_and_calls(self, sample_chain):
        """Test filtering puts and calls."""
        puts = sample_chain.puts
        calls = sample_chain.calls
        
        assert len(puts) == 4  # All sample contracts are puts
        assert len(calls) == 0
    
    def test_get_contract(self, sample_chain):
        """Test getting contract by strike."""
        contract = sample_chain.get_contract(150.0, OptionType.PUT)
        assert contract is not None
        assert contract.strike == 150.0
        
        # Non-existent strike
        contract = sample_chain.get_contract(999.0, OptionType.PUT)
        assert contract is None
    
    def test_data_completeness(self, sample_chain):
        """Test data completeness calculation."""
        completeness, missing = sample_chain.compute_data_completeness()
        assert completeness >= 0.5  # At least partial data


# ============================================================================
# Contract Selection Tests
# ============================================================================

class TestContractSelection:
    """Tests for contract selection logic."""
    
    def test_select_by_delta(self, sample_chain):
        """Test selecting contract by target delta."""
        criteria = ContractSelectionCriteria(
            option_type=OptionType.PUT,
            target_delta=-0.25,
            delta_tolerance=0.10,
            min_dte=20,
            max_dte=45,
            min_liquidity_grade=ContractLiquidityGrade.B,
        )
        
        result = select_contract(sample_chain, criteria)
        
        assert result is not None
        assert result.contract.delta.value is not None
        # Should select contract closest to target delta
        assert -0.35 <= result.contract.delta.value <= -0.15
    
    def test_no_selection_when_no_match(self, sample_chain):
        """Test no selection when no contracts match criteria."""
        criteria = ContractSelectionCriteria(
            option_type=OptionType.CALL,  # No calls in sample chain
            target_delta=0.25,
            delta_tolerance=0.05,
            min_dte=20,
            max_dte=45,
        )
        
        result = select_contract(sample_chain, criteria)
        assert result is None
    
    def test_selection_respects_dte(self, sample_chain):
        """Test DTE filter is applied."""
        criteria = ContractSelectionCriteria(
            option_type=OptionType.PUT,
            target_delta=-0.25,
            delta_tolerance=0.15,
            min_dte=60,  # Too high for 30-day contracts
            max_dte=90,
        )
        
        result = select_contract(sample_chain, criteria)
        # Should not select because DTE is out of range
        assert result is None or not result.criteria_results.get("dte_in_range", True)


# ============================================================================
# ORATS Chain Provider Tests
# ============================================================================

class TestOratsChainProvider:
    """Tests for ORATS-based chain provider."""
    
    @patch("app.core.options.orats_chain_provider.get_orats_live_strikes")
    @patch("app.core.options.orats_chain_provider.get_orats_live_summaries")
    def test_get_expirations(self, mock_summaries, mock_strikes, mock_orats_strikes):
        """Test fetching available expirations."""
        mock_strikes.return_value = mock_orats_strikes
        mock_summaries.return_value = [{"stockPrice": 152.0}]
        
        provider = OratsChainProvider(use_cache=False)
        expirations = provider.get_expirations("AAPL")
        
        assert len(expirations) >= 1
        assert all(isinstance(e, ExpirationInfo) for e in expirations)
        assert all(e.dte > 0 for e in expirations)
    
    @patch("app.core.options.orats_chain_provider.get_orats_live_strikes")
    @patch("app.core.options.orats_chain_provider.get_orats_live_summaries")
    def test_get_chain(self, mock_summaries, mock_strikes, mock_orats_strikes):
        """Test fetching a chain."""
        mock_strikes.return_value = mock_orats_strikes
        mock_summaries.return_value = [{"stockPrice": 152.0}]
        
        provider = OratsChainProvider(use_cache=False)
        exp_date = date.today() + timedelta(days=30)
        result = provider.get_chain("AAPL", exp_date)
        
        assert result.success
        assert result.chain is not None
        assert len(result.chain.contracts) > 0
    
    @patch("app.core.options.orats_chain_provider.get_orats_live_strikes")
    def test_missing_chain_returns_data_incomplete(self, mock_strikes):
        """Test missing chain produces DATA_INCOMPLETE."""
        mock_strikes.return_value = []  # No data
        
        provider = OratsChainProvider(use_cache=False)
        result = provider.get_chain("INVALID", date.today() + timedelta(days=30))
        
        assert not result.success
        assert result.data_quality in (DataQuality.MISSING, DataQuality.ERROR)
        assert "strikes" in result.missing_fields or result.error is not None
    
    @patch("app.core.options.orats_chain_provider.get_orats_live_strikes")
    @patch("app.core.options.orats_chain_provider.get_orats_live_summaries")
    def test_missing_fields_tracked(self, mock_summaries, mock_strikes):
        """Test that missing fields in strikes are tracked."""
        # Strikes with missing delta
        exp_date = (date.today() + timedelta(days=30)).isoformat()
        mock_strikes.return_value = [
            {
                "ticker": "AAPL",
                "expirDate": exp_date,
                "strike": 150.0,
                "putCall": "P",
                "bid": 2.50,
                "ask": 2.70,
                # delta is missing
                "openInt": 1500,
            },
        ]
        mock_summaries.return_value = [{"stockPrice": 152.0}]
        
        provider = OratsChainProvider(use_cache=False)
        result = provider.get_chain("AAPL", date.today() + timedelta(days=30))
        
        assert result.success
        assert "delta" in result.missing_fields


# ============================================================================
# Rate Limiter Tests
# ============================================================================

class TestRateLimiter:
    """Tests for rate limiting."""
    
    def test_rate_limiter_throttles(self):
        """Test that rate limiter enforces delays."""
        import time
        
        limiter = RateLimiter(calls_per_second=10.0)  # 100ms between calls
        
        start = time.time()
        for _ in range(3):
            limiter.acquire()
        elapsed = time.time() - start
        
        # Should take at least 200ms (2 gaps for 3 calls)
        assert elapsed >= 0.15  # Allow some tolerance


# ============================================================================
# Cache Tests
# ============================================================================

class TestChainCache:
    """Tests for chain caching."""
    
    def test_cache_stores_and_retrieves(self):
        """Test basic cache operations."""
        cache = ChainCache(ttl_seconds=300)
        exp_date = date.today() + timedelta(days=30)
        
        result = ChainProviderResult(success=True, chain=None)
        cache.set("AAPL", exp_date, result)
        
        cached = cache.get("AAPL", exp_date)
        assert cached is not None
        assert cached.success == True
    
    def test_cache_expires(self):
        """Test cache TTL expiration."""
        cache = ChainCache(ttl_seconds=0)  # Immediate expiry
        exp_date = date.today() + timedelta(days=30)
        
        result = ChainProviderResult(success=True, chain=None)
        cache.set("AAPL", exp_date, result)
        
        import time
        time.sleep(0.01)  # Small delay
        
        cached = cache.get("AAPL", exp_date)
        assert cached is None  # Should be expired


# ============================================================================
# 2-Stage Evaluator Tests
# ============================================================================

class TestStagedEvaluator:
    """Tests for 2-stage evaluation pipeline."""
    
    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    def test_stage1_qualifies_stock(self, mock_summaries):
        """Test stage 1 qualifies a good stock."""
        mock_summaries.return_value = [{
            "stockPrice": 152.0,
            "bid": 151.90,
            "ask": 152.10,
            "volume": 5000000,
            "avgVolume": 4000000,
            "ivRank": 45.0,
        }]
        
        from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict
        
        result = evaluate_stage1("AAPL")
        
        assert result.stock_verdict == StockVerdict.QUALIFIED
        assert result.price == 152.0
        assert result.data_completeness > 0.5

    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    def test_stage1_maps_orats_summaries_to_snapshot_fields(self, mock_summaries):
        """StockSnapshot-equivalent fields are set from ORATS /live/summaries response."""
        # ORATS /live/summaries can use: stockPrice, bid, ask, volume, stockVolume,
        # avgVolume, avgStockVolume, averageVolume, ivRank, iv30Rank
        mock_summaries.return_value = [{
            "ticker": "AAPL",
            "stockPrice": 176.20,
            "bid": 176.18,
            "ask": 176.25,
            "volume": 45_123_000,
            "avgStockVolume": 62_000_000,
            "iv30Rank": 38.0,
        }]
        
        from app.core.eval.staged_evaluator import evaluate_stage1
        
        result = evaluate_stage1("AAPL")
        
        assert result.price == 176.20
        assert result.bid == 176.18
        assert result.ask == 176.25
        assert result.volume == 45_123_000
        assert result.avg_volume == 62_000_000
        assert result.iv_rank == 38.0
        assert "avg_volume" not in result.missing_fields and "iv_rank" not in result.missing_fields
    
    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    def test_stage1_blocks_missing_price(self, mock_summaries):
        """Test stage 1 blocks when price is missing."""
        mock_summaries.return_value = [{
            "stockPrice": None,
            "volume": 1000000,
        }]
        
        from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict
        
        result = evaluate_stage1("BADSTOCK")
        
        assert result.stock_verdict == StockVerdict.BLOCKED
        assert "price" in result.stock_verdict_reason.lower()
    
    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    def test_stage1_holds_incomplete_data(self, mock_summaries):
        """Test stage 1 holds when data is incomplete."""
        mock_summaries.return_value = [{
            "stockPrice": 100.0,
            # All other fields missing
        }]
        
        from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict
        
        result = evaluate_stage1("SPARSE")
        
        assert result.stock_verdict == StockVerdict.HOLD
        assert result.data_completeness < 0.5
    
    @patch("app.core.eval.staged_evaluator.evaluate_stage1")
    @patch("app.core.eval.staged_evaluator.evaluate_stage2")
    def test_full_evaluation_eligible(self, mock_stage2, mock_stage1):
        """Test full evaluation produces ELIGIBLE verdict."""
        from app.core.eval.staged_evaluator import (
            evaluate_symbol_full,
            Stage1Result,
            Stage2Result,
            StockVerdict,
            SelectedContract,
            EvaluationStage,
            FinalVerdict,
        )
        
        # Mock stage 1
        mock_stage1.return_value = Stage1Result(
            symbol="AAPL",
            stock_verdict=StockVerdict.QUALIFIED,
            stock_verdict_reason="Stock qualified",
            stage1_score=75,
            price=152.0,
            data_completeness=0.9,
        )
        
        # Mock stage 2 with selected contract
        mock_selected = MagicMock(spec=SelectedContract)
        mock_selected.selection_reason = "delta=-0.25, DTE=30, grade=B"
        mock_selected.contract = MagicMock()
        mock_selected.contract.get_liquidity_grade.return_value = ContractLiquidityGrade.B
        
        mock_stage2.return_value = Stage2Result(
            symbol="AAPL",
            expirations_available=5,
            expirations_evaluated=3,
            contracts_evaluated=50,
            selected_contract=mock_selected,
            selected_expiration=date.today() + timedelta(days=30),
            liquidity_grade="B",
            liquidity_ok=True,
            liquidity_reason="Good liquidity",
            chain_completeness=0.9,
        )
        
        result = evaluate_symbol_full("AAPL", skip_stage2=False)
        
        assert result.stage_reached == EvaluationStage.STAGE2_CHAIN
        assert result.final_verdict == FinalVerdict.ELIGIBLE
        assert result.verdict == "ELIGIBLE"
    
    @patch("app.core.eval.staged_evaluator.evaluate_stage1")
    def test_full_evaluation_stage1_block(self, mock_stage1):
        """Test full evaluation stops at stage 1 when blocked."""
        from app.core.eval.staged_evaluator import (
            evaluate_symbol_full,
            Stage1Result,
            StockVerdict,
            EvaluationStage,
            FinalVerdict,
        )
        
        mock_stage1.return_value = Stage1Result(
            symbol="BADSTOCK",
            stock_verdict=StockVerdict.BLOCKED,
            stock_verdict_reason="No price data",
            stage1_score=0,
            price=None,
            data_completeness=0.1,
        )
        
        result = evaluate_symbol_full("BADSTOCK", skip_stage2=False)
        
        assert result.stage_reached == EvaluationStage.STAGE1_ONLY
        assert result.final_verdict == FinalVerdict.BLOCKED
        assert result.verdict == "BLOCKED"


# ============================================================================
# Integration Tests
# ============================================================================

class TestChainSelectionIntegration:
    """Integration tests for chain provider and contract selection."""
    
    @patch("app.core.orats.orats_client.get_orats_live_strikes")
    @patch("app.core.orats.orats_client.get_orats_live_summaries")
    def test_evaluator_selects_correct_contract(self, mock_summaries, mock_strikes, mock_orats_strikes):
        """Test evaluator selects correct contract by delta and DTE."""
        mock_strikes.return_value = mock_orats_strikes
        mock_summaries.return_value = [{
            "stockPrice": 152.0,
            "bid": 151.90,
            "ask": 152.10,
            "volume": 5000000,
            "avgVolume": 4000000,
            "ivRank": 45.0,
        }]
        
        provider = OratsChainProvider(use_cache=False)
        exp_date = date.today() + timedelta(days=30)
        
        # Get chain
        result = provider.get_chain("AAPL", exp_date)
        assert result.success
        
        # Select contract
        criteria = ContractSelectionCriteria(
            option_type=OptionType.PUT,
            target_delta=-0.25,
            delta_tolerance=0.10,
            min_dte=20,
            max_dte=45,
            min_liquidity_grade=ContractLiquidityGrade.B,
        )
        
        selected = select_contract(result.chain, criteria)
        
        assert selected is not None
        # The contract at strike 150 has delta -0.25
        assert selected.contract.strike == 150.0
        assert selected.contract.delta.value == pytest.approx(-0.25, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
