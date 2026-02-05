# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for ORATS Delayed Data API - Strikes-by-OPRA module.

Tests cover:
- Option symbol generation (OCC format, NO space padding)
- Client parameter names (tickers plural for /strikes/options)
- Response parsing (JSON["data"] extraction)
- Schema validation (optionSymbol, bidPrice, askPrice, openInterest)
- OCC-only invariant: get_strikes_by_opra rejects underlying ticker (raises).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch, MagicMock
import pytest

from app.core.orats.orats_opra import (
    # Symbol helpers
    to_yymmdd,
    build_orats_option_symbol,
    validate_orats_option_symbol,
    is_occ_option_symbol,
    parse_orats_option_symbol,
    # Client
    OratsDelayedClient,
    OratsDelayedError,
    # Data classes
    OptionContract,
    UnderlyingQuote,
    OpraEnrichmentResult,
    # High-level functions
    fetch_opra_enrichment,
    check_opra_liquidity_gate,
)


# ============================================================================
# Test Option Symbol Generation
# ============================================================================

class TestOptionSymbolGeneration:
    """Tests for OCC option symbol building."""

    def test_to_yymmdd(self):
        """Test date conversion to YYMMDD format."""
        assert to_yymmdd("2026-02-20") == "260220"
        assert to_yymmdd("2023-09-15") == "230915"
        assert to_yymmdd("2030-12-31") == "301231"

    def test_build_option_symbol_put(self):
        """Test PUT option symbol generation."""
        # AAPL + 2026-02-20 + P + 275.0 => AAPL260220P00275000
        result = build_orats_option_symbol("AAPL", "2026-02-20", "P", 275.0)
        assert result == "AAPL260220P00275000"

    def test_build_option_symbol_call(self):
        """Test CALL option symbol generation."""
        result = build_orats_option_symbol("AAPL", "2023-09-15", "C", 175.0)
        assert result == "AAPL230915C00175000"

    def test_build_option_symbol_decimal_strike(self):
        """Test option symbol with decimal strike (e.g., 450.50)."""
        result = build_orats_option_symbol("SPY", "2026-03-20", "P", 450.50)
        assert result == "SPY260320P00450500"

    def test_build_option_symbol_no_space_padding(self):
        """CRITICAL: Verify NO space padding on root (per ORATS examples)."""
        result = build_orats_option_symbol("AAPL", "2026-03-20", "P", 175.0)
        # Should NOT contain spaces
        assert " " not in result
        # Should start with AAPL directly followed by date
        assert result.startswith("AAPL26")

    def test_build_option_symbol_short_ticker(self):
        """Test with short ticker (no padding)."""
        result = build_orats_option_symbol("V", "2026-03-20", "C", 300.0)
        assert result == "V260320C00300000"

    def test_build_option_symbol_long_ticker(self):
        """Test with longer ticker."""
        result = build_orats_option_symbol("GOOGL", "2026-03-20", "P", 150.0)
        assert result == "GOOGL260320P00150000"

    def test_build_option_symbol_strike_rounding(self):
        """Test strike rounding for fractional strikes."""
        # 175.005 should round to 175005
        result = build_orats_option_symbol("AAPL", "2026-03-20", "P", 175.005)
        assert result == "AAPL260320P00175005"
        
        # 175.0049 should round to 175005
        result = build_orats_option_symbol("AAPL", "2026-03-20", "P", 175.0049)
        assert result == "AAPL260320P00175005"

    def test_validate_option_symbol_valid(self):
        """Test validation of valid option symbols."""
        assert validate_orats_option_symbol("AAPL260220P00275000") == True
        assert validate_orats_option_symbol("SPY260320C00450500") == True
        assert validate_orats_option_symbol("V260320C00300000") == True

    def test_validate_option_symbol_invalid(self):
        """Test validation of invalid option symbols."""
        assert validate_orats_option_symbol("") == False
        assert validate_orats_option_symbol("AAPL") == False
        assert validate_orats_option_symbol("AAPL260320") == False
        assert validate_orats_option_symbol("AAPL260320X00175000") == False  # Invalid type

    def test_is_occ_option_symbol_accepts_valid(self):
        """is_occ_option_symbol accepts OCC format (unpadded and space-padded root)."""
        assert is_occ_option_symbol("AAPL260320P00175000") == True
        assert is_occ_option_symbol("AAPL  260320P00175000") == True
        assert is_occ_option_symbol("SPY260320C00450500") == True

    def test_is_occ_option_symbol_rejects_underlying(self):
        """is_occ_option_symbol rejects underlying tickers (forbidden for /strikes/options)."""
        assert is_occ_option_symbol("AAPL") == False
        assert is_occ_option_symbol("SPY") == False
        assert is_occ_option_symbol("") == False
        assert is_occ_option_symbol("AAPL260320") == False

    def test_parse_option_symbol(self):
        """Test parsing option symbol into components."""
        result = parse_orats_option_symbol("AAPL260220P00275000")
        
        assert result is not None
        assert result["root"] == "AAPL"
        assert result["expir_date"] == "2026-02-20"
        assert result["option_type"] == "PUT"
        assert result["strike"] == 275.0

    def test_parse_option_symbol_call(self):
        """Test parsing CALL option symbol."""
        result = parse_orats_option_symbol("SPY260320C00450500")
        
        assert result is not None
        assert result["root"] == "SPY"
        assert result["option_type"] == "CALL"
        assert result["strike"] == 450.5


# ============================================================================
# Test Client Parameter Names
# ============================================================================

class TestClientParameterNames:
    """Tests to ensure correct parameter names are used."""

    def test_strikes_uses_ticker_singular(self):
        """Test /strikes uses 'ticker' (singular) parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"ticker": "AAPL", "strike": 175.0}]}
        
        with patch("app.core.orats.orats_opra.requests.get") as mock_get:
            mock_get.return_value = mock_response
            
            client = OratsDelayedClient()
            client.get_strikes("AAPL")
            
            # Verify the call used 'ticker' param
            call_args = mock_get.call_args
            params = call_args.kwargs.get("params", call_args[1].get("params", {}))
            
            assert "ticker" in params
            assert params["ticker"] == "AAPL"

    def test_strikes_options_uses_tickers_plural(self):
        """CRITICAL: Test /strikes/options uses 'tickers' (PLURAL) parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"optionSymbol": "AAPL260320P00175000"}]}
        
        with patch("app.core.orats.orats_opra.requests.get") as mock_get:
            mock_get.return_value = mock_response
            
            client = OratsDelayedClient()
            client.get_strikes_by_opra(["AAPL260320P00175000"])
            
            # Verify the call used 'tickers' (PLURAL) param
            call_args = mock_get.call_args
            params = call_args.kwargs.get("params", call_args[1].get("params", {}))
            
            assert "tickers" in params  # MUST be plural
            assert "ticker" not in params  # Must NOT use singular


# ============================================================================
# Test Response Parsing
# ============================================================================

class TestResponseParsing:
    """Tests for response parsing and data extraction."""

    def test_parse_json_data_list(self):
        """Test parsing JSON with {data: [...]} format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"optionSymbol": "AAPL260320P00175000", "bidPrice": 2.5, "askPrice": 2.6},
                {"optionSymbol": "AAPL260320P00170000", "bidPrice": 1.8, "askPrice": 1.9},
            ]
        }
        
        with patch("app.core.orats.orats_opra.requests.get") as mock_get:
            mock_get.return_value = mock_response
            
            client = OratsDelayedClient()
            rows = client.get_strikes_by_opra(["AAPL260320P00175000"])
            
            assert len(rows) == 2
            assert rows[0]["optionSymbol"] == "AAPL260320P00175000"

    def test_parse_json_raw_list(self):
        """Test parsing JSON that is a raw list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"optionSymbol": "AAPL260320P00175000", "bidPrice": 2.5},
        ]
        
        with patch("app.core.orats.orats_opra.requests.get") as mock_get:
            mock_get.return_value = mock_response
            
            client = OratsDelayedClient()
            rows = client.get_strikes_by_opra(["AAPL260320P00175000"])
            
            assert len(rows) == 1


# ============================================================================
# Test Schema Validation (Option + Underlying Rows)
# ============================================================================

class TestSchemaValidation:
    """Tests for schema validation and row categorization."""

    def test_option_row_has_required_fields(self):
        """Test option row contains required OPRA fields (OCC-only call, no underlying row)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "optionSymbol": "AAPL260320P00175000",
                    "ticker": "AAPL",
                    "expirDate": "2026-03-20",
                    "strike": 175.0,
                    "bidPrice": 2.50,
                    "askPrice": 2.60,
                    "volume": 500,
                    "openInterest": 5000,
                    "delta": -0.25,
                    "gamma": 0.05,
                    "theta": -0.03,
                    "vega": 0.15,
                    "quoteDate": "2026-02-04",
                },
            ]
        }
        
        with patch("app.core.orats.orats_opra.requests.get") as mock_get:
            mock_get.return_value = mock_response
            
            client = OratsDelayedClient()
            rows = client.get_strikes_by_opra(["AAPL260320P00175000"])
            
            assert len(rows) == 1
            option_row = rows[0]
            assert "optionSymbol" in option_row
            assert "bidPrice" in option_row
            assert "askPrice" in option_row
            assert "openInterest" in option_row

    def test_merger_extracts_options_underlying_from_strikes(self):
        """Enrichment extracts options from OPRA; underlying quote from strikes (stock price only)."""
        strikes_response = MagicMock()
        strikes_response.status_code = 200
        strikes_response.json.return_value = {
            "data": [
                {"expirDate": "2026-03-20", "strike": 175.0, "stockPrice": 180.0},
                {"expirDate": "2026-03-20", "strike": 170.0, "stockPrice": 180.0},
            ]
        }
        
        opra_response = MagicMock()
        opra_response.status_code = 200
        opra_response.json.return_value = {
            "data": [
                {"optionSymbol": "AAPL260320P00175000", "bidPrice": 2.5, "askPrice": 2.6, "openInterest": 5000, "dte": 30},
                {"optionSymbol": "AAPL260320P00170000", "bidPrice": 1.8, "askPrice": 1.9, "openInterest": 4000, "dte": 30},
            ]
        }
        
        def mock_get(url, **kwargs):
            if "/strikes/options" in url:
                return opra_response
            return strikes_response
        
        with patch("app.core.orats.orats_opra.requests.get", side_effect=mock_get):
            result = fetch_opra_enrichment("AAPL", dte_min=30, dte_max=45)
            
            assert result.underlying is not None
            assert result.underlying.symbol == "AAPL"
            assert result.underlying.stock_price == 180.0
            
            assert len(result.options) == 2
            assert result.options[0].option_symbol == "AAPL260320P00175000"
            assert result.options[0].bid_price == 2.5
            assert result.options[0].open_interest == 5000


# ============================================================================
# Test OptionContract Properties
# ============================================================================

class TestOptionContract:
    """Tests for OptionContract dataclass."""

    def test_has_valid_liquidity_true(self):
        """Test contract with valid liquidity."""
        contract = OptionContract(
            symbol="AAPL",
            option_symbol="AAPL260320P00175000",
            expir_date="2026-03-20",
            strike=175.0,
            option_type="PUT",
            dte=30,
            bid_price=2.50,
            ask_price=2.60,
            open_interest=5000,
        )
        
        assert contract.has_valid_liquidity == True
        assert contract.mid_price == pytest.approx(2.55)
        assert contract.spread == pytest.approx(0.10)

    def test_has_valid_liquidity_false_no_oi(self):
        """Test contract without open interest."""
        contract = OptionContract(
            symbol="AAPL",
            option_symbol="AAPL260320P00175000",
            expir_date="2026-03-20",
            strike=175.0,
            option_type="PUT",
            dte=30,
            bid_price=2.50,
            ask_price=2.60,
            open_interest=0,  # Zero OI
        )
        
        assert contract.has_valid_liquidity == False

    def test_has_valid_liquidity_false_no_bid(self):
        """Test contract without bid."""
        contract = OptionContract(
            symbol="AAPL",
            option_symbol="AAPL260320P00175000",
            expir_date="2026-03-20",
            strike=175.0,
            option_type="PUT",
            dte=30,
            bid_price=None,
            ask_price=2.60,
            open_interest=5000,
        )
        
        assert contract.has_valid_liquidity == False


# ============================================================================
# Test Liquidity Gate
# ============================================================================

class TestLiquidityGate:
    """Tests for liquidity gate check."""

    def test_gate_pass(self):
        """Test gate passes with sufficient liquidity."""
        result = OpraEnrichmentResult(
            symbol="AAPL",
            options=[
                OptionContract("AAPL", "AAPL260320P00175000", "2026-03-20", 175.0, "PUT", 30, bid_price=2.5, ask_price=2.6, open_interest=5000),
                OptionContract("AAPL", "AAPL260320P00170000", "2026-03-20", 170.0, "PUT", 30, bid_price=1.8, ask_price=1.9, open_interest=4000),
                OptionContract("AAPL", "AAPL260320P00165000", "2026-03-20", 165.0, "PUT", 30, bid_price=1.2, ask_price=1.3, open_interest=3000),
                OptionContract("AAPL", "AAPL260320C00185000", "2026-03-20", 185.0, "CALL", 30, bid_price=3.0, ask_price=3.1, open_interest=4000),
                OptionContract("AAPL", "AAPL260320C00190000", "2026-03-20", 190.0, "CALL", 30, bid_price=2.0, ask_price=2.1, open_interest=3000),
            ],
        )
        
        passed, reason = check_opra_liquidity_gate(result)
        
        assert passed == True
        assert "PASS" in reason
        assert "3 valid puts" in reason

    def test_gate_fail_insufficient_puts(self):
        """Test gate fails with insufficient puts."""
        result = OpraEnrichmentResult(
            symbol="AAPL",
            options=[
                OptionContract("AAPL", "AAPL260320P00175000", "2026-03-20", 175.0, "PUT", 30, bid_price=2.5, ask_price=2.6, open_interest=5000),
                OptionContract("AAPL", "AAPL260320P00170000", "2026-03-20", 170.0, "PUT", 30, bid_price=1.8, ask_price=1.9, open_interest=4000),
                # Only 2 valid puts
            ],
        )
        
        passed, reason = check_opra_liquidity_gate(result)
        
        assert passed == False
        assert "FAIL" in reason

    def test_gate_fail_with_error(self):
        """Test gate fails when result has error."""
        result = OpraEnrichmentResult(
            symbol="AAPL",
            error="Strikes fetch failed",
        )
        
        passed, reason = check_opra_liquidity_gate(result)
        
        assert passed == False
        assert "FAIL" in reason


# ============================================================================
# Test Full Pipeline (Mocked)
# ============================================================================

class TestFullPipelineMocked:
    """Tests for the full enrichment pipeline."""

    def test_full_pipeline_success(self):
        """Test complete pipeline with mocked responses."""
        # Mock strikes response
        strikes_response = MagicMock()
        strikes_response.status_code = 200
        strikes_response.json.return_value = {
            "data": [
                {"expirDate": "2026-03-20", "strike": 175.0, "stockPrice": 180.0, "dte": 30},
                {"expirDate": "2026-03-20", "strike": 170.0, "stockPrice": 180.0, "dte": 30},
                {"expirDate": "2026-03-20", "strike": 165.0, "stockPrice": 180.0, "dte": 30},
            ]
        }
        
        opra_response = MagicMock()
        opra_response.status_code = 200
        opra_response.json.return_value = {
            "data": [
                {"optionSymbol": "AAPL260320P00175000", "bidPrice": 2.5, "askPrice": 2.6, "openInterest": 5000, "dte": 30},
                {"optionSymbol": "AAPL260320P00170000", "bidPrice": 1.8, "askPrice": 1.9, "openInterest": 4000, "dte": 30},
                {"optionSymbol": "AAPL260320P00165000", "bidPrice": 1.2, "askPrice": 1.3, "openInterest": 3000, "dte": 30},
                {"optionSymbol": "AAPL260320C00175000", "bidPrice": 3.5, "askPrice": 3.6, "openInterest": 4500, "dte": 30},
                {"optionSymbol": "AAPL260320C00170000", "bidPrice": 4.2, "askPrice": 4.3, "openInterest": 4200, "dte": 30},
            ]
        }
        
        def mock_get(url, **kwargs):
            if "/strikes/options" in url:
                return opra_response
            return strikes_response
        
        with patch("app.core.orats.orats_opra.requests.get", side_effect=mock_get):
            result = fetch_opra_enrichment("AAPL", dte_min=30, dte_max=45)
            
            assert result.error is None
            assert result.strikes_rows == 3
            assert result.underlying is not None
            assert result.underlying.stock_price == 180.0
            assert len(result.valid_puts) == 3
            assert len(result.valid_calls) == 2
            assert result.total_valid == 5
            
            passed, reason = check_opra_liquidity_gate(result)
            assert passed == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
