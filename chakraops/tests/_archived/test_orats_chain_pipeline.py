# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for ORATS option chain pipeline (two-step architecture).

Tests validate the correct ORATS integration:
  STEP 1: /datav2/strikes → base chain
  STEP 2: /datav2/strikes/options?tickers=OPRA1,... → liquidity enrichment (param is 'tickers' plural)
  STEP 3: Merge results

Also tests:
  - ORATS_DATA_MODE env var and mode selection
  - live_derived fail-fast guard
  - Bounded strike selection

NOTE: Capability probe tests removed - we now always use 'tickers' (plural) per ORATS docs.
For new code, use app.core.orats.orats_opra module which is the clean implementation.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock
import pytest

from app.core.options.orats_chain_pipeline import (
    # Data mode
    OratsDataMode,
    # Errors
    OratsChainError,
    OratsOpraModeError,
    # Data models
    BaseContract,
    EnrichedContract,
    OptionChainResult,
    # Pipeline functions
    fetch_base_chain,
    build_opra_symbols,
    fetch_enriched_contracts,
    merge_chain_and_liquidity,
    fetch_option_chain,
    check_liquidity_gate,
    # Parameter name (now always returns 'tickers')
    get_strikes_options_param_name,
)


# ============================================================================
# Test Data Mode Configuration
# ============================================================================

class TestOratsDataMode:
    """Tests for ORATS data mode configuration."""

    def test_get_mode_default_is_delayed(self):
        """Test default mode is 'delayed' when env var not set."""
        # Clear env var if set
        if "ORATS_DATA_MODE" in os.environ:
            del os.environ["ORATS_DATA_MODE"]
        
        mode = OratsDataMode.get_current_mode()
        assert mode == "delayed"

    def test_get_mode_from_env(self):
        """Test mode is read from ORATS_DATA_MODE env var."""
        os.environ["ORATS_DATA_MODE"] = "live"
        try:
            mode = OratsDataMode.get_current_mode()
            assert mode == "live"
        finally:
            del os.environ["ORATS_DATA_MODE"]

    def test_get_mode_invalid_defaults_to_delayed(self):
        """Test invalid mode defaults to 'delayed'."""
        os.environ["ORATS_DATA_MODE"] = "invalid_mode"
        try:
            mode = OratsDataMode.get_current_mode()
            assert mode == "delayed"
        finally:
            del os.environ["ORATS_DATA_MODE"]

    def test_base_urls(self):
        """Test correct base URLs for each mode."""
        assert OratsDataMode.BASE_URLS["delayed"] == "https://api.orats.io/datav2"
        assert OratsDataMode.BASE_URLS["live"] == "https://api.orats.io/datav2/live"
        assert OratsDataMode.BASE_URLS["live_derived"] == "https://api.orats.io/datav2/live/derived"

    def test_supports_opra_fields_delayed(self):
        """Test delayed mode supports OPRA fields."""
        assert OratsDataMode.supports_opra_fields("delayed") == True

    def test_supports_opra_fields_live(self):
        """Test live mode supports OPRA fields."""
        assert OratsDataMode.supports_opra_fields("live") == True

    def test_supports_opra_fields_live_derived(self):
        """Test live_derived mode does NOT support OPRA fields."""
        assert OratsDataMode.supports_opra_fields("live_derived") == False


# ============================================================================
# Test live_derived Fail-Fast Guard
# ============================================================================

class TestLiveDerivedFailFast:
    """Tests for live_derived mode fail-fast guard."""

    def test_fetch_enriched_raises_on_live_derived(self):
        """Test fetch_enriched_contracts raises OratsOpraModeError for live_derived."""
        os.environ["ORATS_DATA_MODE"] = "live_derived"
        try:
            with pytest.raises(OratsOpraModeError) as exc_info:
                fetch_enriched_contracts(["AAPL  260320P00175000"], require_opra_fields=True)
            
            assert "live_derived" in str(exc_info.value)
            assert "OPRA" in str(exc_info.value)
        finally:
            del os.environ["ORATS_DATA_MODE"]

    def test_fetch_option_chain_raises_on_live_derived(self):
        """Test fetch_option_chain raises OratsOpraModeError for live_derived."""
        os.environ["ORATS_DATA_MODE"] = "live_derived"
        try:
            with pytest.raises(OratsOpraModeError) as exc_info:
                fetch_option_chain("AAPL")
            
            assert "live_derived" in str(exc_info.value)
        finally:
            del os.environ["ORATS_DATA_MODE"]

    def test_opra_mode_error_has_helpful_message(self):
        """Test OratsOpraModeError has a helpful error message."""
        error = OratsOpraModeError("live_derived")
        
        assert "live_derived" in str(error)
        assert "OPRA" in str(error)
        assert "delayed" in str(error) or "live" in str(error)


# ============================================================================
# Test Parameter Name Function
# ============================================================================

class TestParameterName:
    """Tests for the strikes/options parameter name function."""

    def test_always_returns_tickers_plural(self):
        """Test function always returns 'tickers' (plural) per ORATS docs."""
        param_name = get_strikes_options_param_name()
        
        # Per ORATS Delayed Data API docs, the param is 'tickers' (plural)
        assert param_name == "tickers"
    
    def test_consistent_return_value(self):
        """Test function always returns the same value."""
        param1 = get_strikes_options_param_name()
        param2 = get_strikes_options_param_name()
        
        assert param1 == param2
        assert param1 == "tickers"


# ============================================================================
# Test OCC/OPRA Symbol Generation
# ============================================================================

class TestBaseContract:
    """Tests for BaseContract dataclass and OPRA symbol generation."""

    def test_opra_symbol_format_call(self):
        """Test OPRA symbol generation for a CALL option."""
        contract = BaseContract(
            symbol="AAPL",
            expiration=date(2026, 3, 20),
            strike=175.0,
            option_type="CALL",
            dte=30,
        )
        
        # Expected: "AAPL  260320C00175000"
        assert contract.opra_symbol == "AAPL  260320C00175000"

    def test_opra_symbol_format_put(self):
        """Test OPRA symbol generation for a PUT option."""
        contract = BaseContract(
            symbol="SPY",
            expiration=date(2026, 4, 17),
            strike=450.50,
            option_type="PUT",
            dte=45,
        )
        
        # Expected: "SPY   260417P00450500"
        assert contract.opra_symbol == "SPY   260417P00450500"

    def test_opra_symbol_long_ticker(self):
        """Test OPRA symbol for ticker exactly 6 chars."""
        contract = BaseContract(
            symbol="GOOGL",
            expiration=date(2026, 3, 20),
            strike=150.0,
            option_type="CALL",
            dte=30,
        )
        
        # GOOGL is 5 chars, should be padded to 6
        assert contract.opra_symbol.startswith("GOOGL ")
        assert len(contract.opra_symbol) == 21  # 6 + 6 + 1 + 8


# ============================================================================
# Test Enriched Contract
# ============================================================================

class TestEnrichedContract:
    """Tests for EnrichedContract with liquidity data."""

    def test_has_valid_liquidity_true(self):
        """Test contract with full liquidity data."""
        contract = EnrichedContract(
            symbol="AAPL",
            expiration=date(2026, 3, 20),
            strike=175.0,
            option_type="PUT",
            opra_symbol="AAPL  260320P00175000",
            dte=30,
            bid=2.50,
            ask=2.60,
            mid=2.55,
            open_interest=5000,
            enriched=True,
        )
        
        assert contract.has_valid_liquidity == True
        assert contract.spread == pytest.approx(0.10)
        assert contract.mid == pytest.approx(2.55)

    def test_has_valid_liquidity_false_no_enrichment(self):
        """Test contract without enrichment data."""
        contract = EnrichedContract(
            symbol="AAPL",
            expiration=date(2026, 3, 20),
            strike=175.0,
            option_type="PUT",
            opra_symbol="AAPL  260320P00175000",
            dte=30,
            enriched=False,
        )
        
        assert contract.has_valid_liquidity == False

    def test_has_valid_liquidity_false_zero_oi(self):
        """Test contract with zero open interest."""
        contract = EnrichedContract(
            symbol="AAPL",
            expiration=date(2026, 3, 20),
            strike=175.0,
            option_type="PUT",
            opra_symbol="AAPL  260320P00175000",
            dte=30,
            bid=2.50,
            ask=2.60,
            open_interest=0,
            enriched=True,
        )
        
        assert contract.has_valid_liquidity == False


# ============================================================================
# Test Build OPRA Symbols
# ============================================================================

class TestBuildOpraSymbols:
    """Tests for OPRA symbol building."""

    def test_build_opra_symbols_creates_mapping(self):
        """Test that OPRA symbols are correctly mapped to contracts."""
        contracts = [
            BaseContract("AAPL", date(2026, 3, 20), 175.0, "PUT", 30),
            BaseContract("AAPL", date(2026, 3, 20), 175.0, "CALL", 30),
            BaseContract("AAPL", date(2026, 3, 20), 180.0, "PUT", 30),
        ]
        
        opra_map = build_opra_symbols(contracts)
        
        assert len(opra_map) == 3
        assert "AAPL  260320P00175000" in opra_map
        assert "AAPL  260320C00175000" in opra_map
        assert "AAPL  260320P00180000" in opra_map


# ============================================================================
# Test Merge Chain and Liquidity
# ============================================================================

class TestMergeChainAndLiquidity:
    """Tests for merging base chain with liquidity enrichment."""

    def test_merge_with_enrichment(self):
        """Test merging when enrichment data exists."""
        base_contracts = [
            BaseContract("AAPL", date(2026, 3, 20), 175.0, "PUT", 30, delta=-0.25),
        ]
        
        enrichment_map = {
            "AAPL  260320P00175000": {
                "bid": 2.50,
                "ask": 2.60,
                "volume": 500,
                "open_interest": 5000,
                "delta": -0.26,
                "iv": 0.35,
            }
        }
        
        merged = merge_chain_and_liquidity(
            base_contracts, enrichment_map, 180.0, "2026-02-04T12:00:00Z"
        )
        
        assert len(merged) == 1
        contract = merged[0]
        assert contract.enriched == True
        assert contract.bid == 2.50
        assert contract.ask == 2.60
        assert contract.open_interest == 5000
        assert contract.delta == -0.26
        assert contract.has_valid_liquidity == True

    def test_merge_without_enrichment(self):
        """Test merging when no enrichment data exists."""
        base_contracts = [
            BaseContract("AAPL", date(2026, 3, 20), 175.0, "PUT", 30, delta=-0.25),
        ]
        
        enrichment_map = {}
        
        merged = merge_chain_and_liquidity(
            base_contracts, enrichment_map, 180.0, "2026-02-04T12:00:00Z"
        )
        
        assert len(merged) == 1
        contract = merged[0]
        assert contract.enriched == False
        assert contract.bid is None
        assert contract.ask is None
        assert contract.delta == -0.25
        assert contract.has_valid_liquidity == False


# ============================================================================
# Test Liquidity Gate
# ============================================================================

class TestLiquidityGate:
    """Tests for liquidity gate checks."""

    def test_gate_pass_sufficient_liquidity(self):
        """Test gate passes with sufficient liquidity."""
        contracts = [
            EnrichedContract(
                symbol="AAPL", expiration=date(2026, 3, 20), strike=175.0,
                option_type="PUT", opra_symbol="AAPL  260320P00175000", dte=30,
                bid=2.50, ask=2.60, open_interest=5000, enriched=True,
            ),
            EnrichedContract(
                symbol="AAPL", expiration=date(2026, 3, 20), strike=170.0,
                option_type="PUT", opra_symbol="AAPL  260320P00170000", dte=30,
                bid=1.80, ask=1.90, open_interest=4000, enriched=True,
            ),
            EnrichedContract(
                symbol="AAPL", expiration=date(2026, 3, 20), strike=165.0,
                option_type="PUT", opra_symbol="AAPL  260320P00165000", dte=30,
                bid=1.20, ask=1.30, open_interest=3000, enriched=True,
            ),
            EnrichedContract(
                symbol="AAPL", expiration=date(2026, 3, 20), strike=185.0,
                option_type="CALL", opra_symbol="AAPL  260320C00185000", dte=30,
                bid=3.00, ask=3.10, open_interest=4000, enriched=True,
            ),
            EnrichedContract(
                symbol="AAPL", expiration=date(2026, 3, 20), strike=190.0,
                option_type="CALL", opra_symbol="AAPL  260320C00190000", dte=30,
                bid=2.00, ask=2.10, open_interest=3000, enriched=True,
            ),
        ]
        
        valid_count = sum(1 for c in contracts if c.has_valid_liquidity)
        
        chain = OptionChainResult(
            symbol="AAPL",
            contracts=contracts,
            contracts_with_liquidity=valid_count,
        )
        
        passed, reason = check_liquidity_gate(chain)
        
        assert passed == True, f"Expected PASS but got: {reason}"
        assert "PASS" in reason

    def test_gate_fail_insufficient_puts(self):
        """Test gate fails with insufficient valid puts."""
        chain = OptionChainResult(
            symbol="AAPL",
            contracts=[
                EnrichedContract(
                    symbol="AAPL", expiration=date(2026, 3, 20), strike=175.0,
                    option_type="PUT", opra_symbol="AAPL  260320P00175000", dte=30,
                    bid=2.50, ask=2.60, open_interest=5000, enriched=True,
                ),
                EnrichedContract(
                    symbol="AAPL", expiration=date(2026, 3, 20), strike=170.0,
                    option_type="PUT", opra_symbol="AAPL  260320P00170000", dte=30,
                    bid=1.80, ask=1.90, open_interest=4000, enriched=True,
                ),
            ],
        )
        
        passed, reason = check_liquidity_gate(chain)
        
        assert passed == False
        assert "FAIL" in reason
        assert "puts" in reason.lower()

    def test_gate_fail_no_contracts(self):
        """Test gate fails with no contracts."""
        chain = OptionChainResult(
            symbol="AAPL",
            contracts=[],
        )
        
        passed, reason = check_liquidity_gate(chain)
        
        assert passed == False
        assert "FAIL" in reason

    def test_gate_fail_with_error(self):
        """Test gate fails when chain has error."""
        chain = OptionChainResult(
            symbol="AAPL",
            error="Base chain fetch failed",
        )
        
        passed, reason = check_liquidity_gate(chain)
        
        assert passed == False
        assert "FAIL" in reason


# ============================================================================
# Test Fetch Base Chain (Mocked)
# ============================================================================

class TestFetchBaseChainMocked:
    """Tests for fetch_base_chain with mocked ORATS API."""

    def test_fetch_base_chain_success(self):
        """Test successful base chain fetch."""
        # Ensure default mode
        if "ORATS_DATA_MODE" in os.environ:
            del os.environ["ORATS_DATA_MODE"]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "expirDate": "2026-03-20",
                "strike": 175.0,
                "dte": 30,
                "stockPrice": 180.0,
                "delta": 0.40,
            },
            {
                "expirDate": "2026-03-20",
                "strike": 180.0,
                "dte": 30,
                "stockPrice": 180.0,
                "delta": 0.50,
            },
        ]
        
        with patch("app.core.options.orats_chain_pipeline.requests.get") as mock_get:
            mock_get.return_value = mock_response
            
            contracts, price, error = fetch_base_chain("AAPL")
            
            assert error is None
            assert price == 180.0
            # With bounded selection, we get both strikes × 2 types = 4 contracts
            assert len(contracts) == 4
            
            puts = [c for c in contracts if c.option_type == "PUT"]
            calls = [c for c in contracts if c.option_type == "CALL"]
            assert len(puts) == 2
            assert len(calls) == 2

    def test_fetch_base_chain_empty_response(self):
        """Test handling of empty response."""
        if "ORATS_DATA_MODE" in os.environ:
            del os.environ["ORATS_DATA_MODE"]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        
        with patch("app.core.options.orats_chain_pipeline.requests.get") as mock_get:
            mock_get.return_value = mock_response
            
            contracts, price, error = fetch_base_chain("AAPL")
            
            assert contracts == []
            assert price is None
            assert error == "No strikes data returned"


# ============================================================================
# Test Fetch Enriched Contracts (Mocked)
# ============================================================================

class TestFetchEnrichedContractsMocked:
    """Tests for fetch_enriched_contracts with mocked ORATS API."""

    def test_fetch_enriched_raises_on_underlying_ticker(self):
        """fetch_enriched_contracts must raise when given underlying ticker (OCC-only)."""
        with pytest.raises(OratsChainError) as exc_info:
            fetch_enriched_contracts(["AAPL"], require_opra_fields=False)
        assert "underlying" in str(exc_info.value).lower() or "forbidden" in str(exc_info.value).lower()

    def test_fetch_enriched_success(self):
        """Test successful enrichment fetch."""
        if "ORATS_DATA_MODE" in os.environ:
            del os.environ["ORATS_DATA_MODE"]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "ticker": "AAPL  260320P00175000",
                "bidPrice": 2.50,
                "askPrice": 2.60,
                "volume": 500,
                "openInt": 5000,
                "delta": -0.25,
                "iv": 0.35,
            },
        ]
        
        with patch("app.core.options.orats_chain_pipeline.requests.get") as mock_get:
            mock_get.return_value = mock_response
            
            opra_symbols = ["AAPL  260320P00175000"]
            enrichment = fetch_enriched_contracts(opra_symbols)
            
            assert len(enrichment) == 1
            assert "AAPL  260320P00175000" in enrichment
            data = enrichment["AAPL  260320P00175000"]
            assert data["bid"] == 2.50
            assert data["ask"] == 2.60
            assert data["open_interest"] == 5000


# ============================================================================
# Test Full Pipeline (Mocked)
# ============================================================================

class TestFullPipelineMocked:
    """Tests for the full pipeline with mocked ORATS API."""

    def test_full_pipeline_success(self):
        """Test full pipeline with both endpoints mocked."""
        if "ORATS_DATA_MODE" in os.environ:
            del os.environ["ORATS_DATA_MODE"]
        
        # Mock /strikes response
        strikes_response = MagicMock()
        strikes_response.status_code = 200
        strikes_response.json.return_value = [
            {"expirDate": "2026-03-20", "strike": 175.0, "dte": 30, "stockPrice": 180.0, "delta": 0.40},
            {"expirDate": "2026-03-20", "strike": 170.0, "dte": 30, "stockPrice": 180.0, "delta": 0.35},
            {"expirDate": "2026-03-20", "strike": 165.0, "dte": 30, "stockPrice": 180.0, "delta": 0.30},
        ]
        
        # Mock /strikes/options response
        options_response = MagicMock()
        options_response.status_code = 200
        options_response.json.return_value = [
            {"ticker": "AAPL  260320P00175000", "bidPrice": 2.50, "askPrice": 2.60, "volume": 500, "openInt": 5000},
            {"ticker": "AAPL  260320P00170000", "bidPrice": 1.80, "askPrice": 1.90, "volume": 400, "openInt": 4000},
            {"ticker": "AAPL  260320P00165000", "bidPrice": 1.20, "askPrice": 1.30, "volume": 300, "openInt": 3000},
        ]
        
        def mock_get(url, **kwargs):
            if "/strikes/options" in url:
                return options_response
            elif "/strikes" in url:
                return strikes_response
            return MagicMock(status_code=404)
        
        with patch("app.core.options.orats_chain_pipeline.requests.get", side_effect=mock_get):
            result = fetch_option_chain("AAPL", enrich_all=False)
            
            assert result.error is None
            assert result.base_chain_count == 6  # 3 strikes * 2 types
            assert result.underlying_price == 180.0
            
            valid_puts = result.valid_puts
            assert len(valid_puts) == 3, f"Expected 3 valid puts, got {len(valid_puts)}"
            
            assert result.contracts_with_liquidity == 3
            
            # Gate check with appropriate thresholds
            passed, reason = check_liquidity_gate(result, min_valid_puts=3, min_valid_contracts=3)
            assert passed == True, f"Expected PASS but got: {reason}"


# ============================================================================
# Test OptionChainResult with Mode Info
# ============================================================================

class TestOptionChainResultMode:
    """Tests for OptionChainResult with data_mode field."""

    def test_result_includes_mode(self):
        """Test that OptionChainResult includes data_mode."""
        result = OptionChainResult(
            symbol="AAPL",
            data_mode="delayed",
        )
        
        assert result.data_mode == "delayed"
        
        result_dict = result.to_dict()
        assert "data_mode" in result_dict
        assert result_dict["data_mode"] == "delayed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
