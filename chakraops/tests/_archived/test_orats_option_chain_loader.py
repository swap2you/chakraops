# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for ORATS option chain loader.

Covers:
1. ORATS payload parsing
2. Partial data handling
3. Liquidity gate PASS/FAIL
4. OptionContractLiquidity dataclass
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock
import pytest

from app.core.options.orats_option_chain_loader import (
    OptionContractLiquidity,
    OptionChainLiquidity,
    load_option_chain_liquidity,
    check_option_liquidity,
)


class TestOptionContractLiquidity:
    """Tests for OptionContractLiquidity frozen dataclass."""

    def test_create_with_full_data(self):
        """Test creating contract with full liquidity data."""
        contract = OptionContractLiquidity(
            symbol="SPY",
            expiration=date(2026, 3, 20),
            strike=450.0,
            option_type="PUT",
            bid=1.50,
            ask=1.55,
            mid=1.525,
            volume=1000,
            open_interest=5000,
            delta=-0.25,
            gamma=0.05,
            theta=-0.03,
            vega=0.10,
            iv=0.20,
            dte=30,
        )
        
        assert contract.symbol == "SPY"
        assert contract.strike == 450.0
        assert contract.option_type == "PUT"
        assert contract.has_valid_liquidity == True
        assert contract.spread == pytest.approx(0.05)
        assert contract.spread_pct == pytest.approx(0.05 / 1.525)

    def test_create_with_missing_data(self):
        """Test creating contract with partial data."""
        contract = OptionContractLiquidity(
            symbol="AAPL",
            expiration=date(2026, 3, 20),
            strike=200.0,
            option_type="CALL",
            bid=None,
            ask=None,
            open_interest=None,
        )
        
        assert contract.has_valid_liquidity == False
        assert contract.spread is None
        assert contract.spread_pct is None

    def test_frozen_immutable(self):
        """Test that dataclass is immutable (frozen)."""
        contract = OptionContractLiquidity(
            symbol="SPY",
            expiration=date(2026, 3, 20),
            strike=450.0,
            option_type="PUT",
        )
        
        with pytest.raises(AttributeError):
            contract.symbol = "AAPL"  # type: ignore

    def test_to_dict(self):
        """Test dictionary serialization."""
        contract = OptionContractLiquidity(
            symbol="SPY",
            expiration=date(2026, 3, 20),
            strike=450.0,
            option_type="PUT",
            bid=1.50,
            ask=1.55,
            open_interest=5000,
        )
        
        d = contract.to_dict()
        assert d["symbol"] == "SPY"
        assert d["expiration"] == "2026-03-20"
        assert d["strike"] == 450.0
        assert d["bid"] == 1.50
        assert d["has_valid_liquidity"] == True


class TestOptionChainLiquidity:
    """Tests for OptionChainLiquidity container."""

    def test_empty_chain(self):
        """Test empty chain properties."""
        chain = OptionChainLiquidity(symbol="SPY")
        
        assert chain.symbol == "SPY"
        assert len(chain.contracts) == 0
        assert chain.liquidity_coverage == 0.0
        assert chain.puts == []
        assert chain.calls == []

    def test_chain_with_contracts(self):
        """Test chain with mixed contracts."""
        put1 = OptionContractLiquidity(
            symbol="SPY",
            expiration=date(2026, 3, 20),
            strike=450.0,
            option_type="PUT",
            bid=1.50,
            ask=1.55,
            open_interest=5000,
        )
        put2 = OptionContractLiquidity(
            symbol="SPY",
            expiration=date(2026, 3, 20),
            strike=445.0,
            option_type="PUT",
            bid=None,  # No liquidity
            ask=None,
            open_interest=None,
        )
        call1 = OptionContractLiquidity(
            symbol="SPY",
            expiration=date(2026, 3, 20),
            strike=450.0,
            option_type="CALL",
            bid=2.00,
            ask=2.10,
            open_interest=3000,
        )
        
        chain = OptionChainLiquidity(
            symbol="SPY",
            contracts=[put1, put2, call1],
        )
        
        assert len(chain.contracts) == 3
        assert len(chain.puts) == 2
        assert len(chain.calls) == 1
        assert len(chain.contracts_with_liquidity) == 2
        assert chain.liquidity_coverage == pytest.approx(2/3)

    def test_filter_by_expiration(self):
        """Test filtering contracts by expiration."""
        exp1 = date(2026, 3, 20)
        exp2 = date(2026, 3, 27)
        
        c1 = OptionContractLiquidity(
            symbol="SPY", expiration=exp1, strike=450.0, option_type="PUT"
        )
        c2 = OptionContractLiquidity(
            symbol="SPY", expiration=exp2, strike=450.0, option_type="PUT"
        )
        
        chain = OptionChainLiquidity(symbol="SPY", contracts=[c1, c2])
        
        filtered = chain.filter_by_expiration(exp1)
        assert len(filtered) == 1
        assert filtered[0].expiration == exp1


class TestLiquidityGatePassFail:
    """Tests for liquidity gate PASS/FAIL scenarios."""

    def test_check_liquidity_pass(self):
        """Test liquidity check passes with valid data."""
        mock_chain = OptionChainLiquidity(
            symbol="SPY",
            contracts=[
                # 5 valid puts
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=450.0,
                    option_type="PUT", bid=1.50, ask=1.55, open_interest=5000,
                    delta=-0.25, dte=30,
                ),
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=445.0,
                    option_type="PUT", bid=1.00, ask=1.05, open_interest=3000,
                    delta=-0.20, dte=30,
                ),
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=440.0,
                    option_type="PUT", bid=0.80, ask=0.85, open_interest=2000,
                    delta=-0.15, dte=30,
                ),
                # Plus some calls
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=450.0,
                    option_type="CALL", bid=2.00, ask=2.10, open_interest=4000,
                    dte=30,
                ),
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=455.0,
                    option_type="CALL", bid=1.50, ask=1.55, open_interest=3500,
                    dte=30,
                ),
            ]
        )
        
        with patch("app.core.options.orats_option_chain_loader.load_option_chain_liquidity") as mock_load:
            mock_load.return_value = mock_chain
            
            passed, reason, chain = check_option_liquidity("SPY")
            
            assert passed == True
            assert "PASS" in reason
            assert chain is not None

    def test_check_liquidity_fail_no_contracts(self):
        """Test liquidity check fails with no contracts."""
        mock_chain = OptionChainLiquidity(
            symbol="SPY",
            contracts=[],
        )
        
        with patch("app.core.options.orats_option_chain_loader.load_option_chain_liquidity") as mock_load:
            mock_load.return_value = mock_chain
            
            passed, reason, chain = check_option_liquidity("SPY")
            
            assert passed == False
            assert "FAIL" in reason

    def test_check_liquidity_fail_insufficient_puts(self):
        """Test liquidity check fails with insufficient valid puts."""
        mock_chain = OptionChainLiquidity(
            symbol="SPY",
            contracts=[
                # 5 contracts with valid liquidity (passes first check)
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=450.0,
                    option_type="PUT", bid=1.50, ask=1.55, open_interest=5000,
                ),
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=445.0,
                    option_type="PUT", bid=1.00, ask=1.05, open_interest=3000,
                ),
                # Only 2 valid puts above, but 3 valid calls
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=450.0,
                    option_type="CALL", bid=2.00, ask=2.10, open_interest=4000,
                ),
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=455.0,
                    option_type="CALL", bid=1.50, ask=1.55, open_interest=3500,
                ),
                OptionContractLiquidity(
                    symbol="SPY", expiration=date(2026, 3, 20), strike=460.0,
                    option_type="CALL", bid=1.00, ask=1.05, open_interest=2000,
                ),
            ]
        )
        
        with patch("app.core.options.orats_option_chain_loader.load_option_chain_liquidity") as mock_load:
            mock_load.return_value = mock_chain
            
            passed, reason, chain = check_option_liquidity("SPY")
            
            assert passed == False
            assert "FAIL" in reason
            assert "PUT" in reason  # Should fail on insufficient puts

    def test_check_liquidity_fail_on_error(self):
        """Test liquidity check fails when loader returns error."""
        mock_chain = OptionChainLiquidity(
            symbol="SPY",
            error="ORATS API unavailable",
        )
        
        with patch("app.core.options.orats_option_chain_loader.load_option_chain_liquidity") as mock_load:
            mock_load.return_value = mock_chain
            
            passed, reason, chain = check_option_liquidity("SPY")
            
            assert passed == False
            assert "FAIL" in reason
            assert "unavailable" in reason.lower() or "error" in reason.lower()


class TestLoadOptionChainLiquidity:
    """Tests for the main loader (delegates to pipeline)."""

    def test_load_returns_chain_on_success(self):
        """Loader returns valid chain when pipeline returns success."""
        from app.core.options.orats_chain_pipeline import (
            OptionChainResult,
            EnrichedContract,
        )
        
        mock_contracts = [
            EnrichedContract(
                symbol="SPY", expiration=date(2026, 3, 20), strike=450.0,
                option_type="PUT", opra_symbol="SPY  260320P00450000", dte=30,
                stock_price=455.0, bid=1.50, ask=1.55, open_interest=5000, enriched=True,
            ),
            EnrichedContract(
                symbol="SPY", expiration=date(2026, 3, 20), strike=450.0,
                option_type="CALL", opra_symbol="SPY  260320C00450000", dte=30,
                stock_price=455.0, bid=2.00, ask=2.10, open_interest=4000, enriched=True,
            ),
        ]
        mock_result = OptionChainResult(
            symbol="SPY", underlying_price=455.0, contracts=mock_contracts,
            base_chain_count=2, opra_symbols_generated=2, enriched_count=2,
            contracts_with_liquidity=2, error=None,
        )
        
        with patch("app.core.options.orats_chain_pipeline.fetch_option_chain") as mock_fetch:
            mock_fetch.return_value = mock_result
            
            chain = load_option_chain_liquidity("SPY")
            
            assert chain.symbol == "SPY"
            assert chain.underlying_price == 455.0
            assert len(chain.contracts) == 2
            assert chain.error is None

    def test_load_handles_empty_response(self):
        """Loader sets error when pipeline returns no contracts."""
        from app.core.options.orats_chain_pipeline import OptionChainResult
        
        mock_result = OptionChainResult(symbol="SPY", contracts=[], error="No strikes data returned")
        
        with patch("app.core.options.orats_chain_pipeline.fetch_option_chain") as mock_fetch:
            mock_fetch.return_value = mock_result
            
            chain = load_option_chain_liquidity("SPY")
            
            assert chain.error is not None
            assert "No strikes" in chain.error or "pipeline" in chain.error.lower()

    def test_load_handles_api_error(self):
        """Loader sets error when pipeline raises."""
        from app.core.options.orats_chain_pipeline import OratsChainError
        
        with patch("app.core.options.orats_chain_pipeline.fetch_option_chain") as mock_fetch:
            mock_fetch.side_effect = OratsChainError("HTTP 500", http_status=500)
            
            chain = load_option_chain_liquidity("SPY")
            
            assert chain.error is not None
            assert "500" in chain.error or "HTTP" in chain.error or "error" in chain.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
