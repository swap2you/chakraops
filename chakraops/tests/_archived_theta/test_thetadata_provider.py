# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for ThetaData market data provider.
ARCHIVED: Moved from tests/legacy/; excluded from pytest via norecursedirs (_archived_theta).

IMPORTANT: These tests are currently DISABLED.

TODO: Re-enable after:
1. Running smoke_thetadata_v3.py successfully with real ThetaTerminal v3
2. Verifying actual HTTP v3 API response schemas for:
   - /stock/trade endpoint (price field names)
   - /stock/daily endpoint (close field names)
   - Response structure and field mappings
3. Updating mocks to match real response structures
4. Confirming all endpoint paths and parameter formats

Current status:
- ThetaData does NOT provide a pip-installable Python SDK
- We use HTTP v3 endpoints directly via httpx
- get_underlying_price() uses /stock/trade and /stock/daily (no snapshot quotes)
- Tests need to be rewritten to mock httpx.Client responses
- Response schemas need to be verified against real API responses

These tests are temporarily disabled due to incorrect API assumptions.
They will be re-enabled once the HTTP v3 integration is fully verified and schemas are finalized.
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.core.market_data.thetadata_provider import ThetaDataProvider
from app.core.market_data.provider import OptionContract

# Legacy: ThetaData provider not used by current ORATS-based pipeline; API structure unverified.
pytestmark = [pytest.mark.legacy, pytest.mark.skip(reason="ThetaData provider not used by current pipeline; API structure unverified (legacy)")]


class TestThetaDataProviderInitialization:
    """Test ThetaData provider initialization."""
    
    @patch.dict("os.environ", {"THETADATA_USERNAME": "test_user", "THETADATA_PASSWORD": "test_pass"})
    @patch("app.core.market_data.thetadata_provider.ThetaClient")
    def test_init_with_env_credentials(self, mock_client_class):
        """Test initialization with environment credentials."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        provider = ThetaDataProvider()
        
        assert provider.username == "test_user"
        assert provider.password == "test_pass"
        mock_client_class.assert_called_once_with(username="test_user", password="test_pass")
    
    @patch("app.core.market_data.thetadata_provider.ThetaClient")
    def test_init_with_explicit_credentials(self, mock_client_class):
        """Test initialization with explicit credentials."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        provider = ThetaDataProvider(username="user", password="pass")
        
        assert provider.username == "user"
        assert provider.password == "pass"
        mock_client_class.assert_called_once_with(username="user", password="pass")
    
    @patch.dict("os.environ", {}, clear=True)
    def test_init_missing_credentials(self):
        """Test initialization fails without credentials."""
        with pytest.raises(ValueError, match="credentials not provided"):
            ThetaDataProvider()
    
    @patch.dict("os.environ", {"THETADATA_USERNAME": "test_user", "THETADATA_PASSWORD": "test_pass"})
    def test_init_missing_thetadata_package(self):
        """Test initialization fails if thetadata package is missing."""
        with patch.dict("sys.modules", {"thetadata": None}):
            with pytest.raises(ImportError, match="thetadata package is not installed"):
                ThetaDataProvider()
    
    @patch.dict("os.environ", {"THETADATA_USERNAME": "test_user", "THETADATA_PASSWORD": "test_pass"})
    @patch("app.core.market_data.thetadata_provider.ThetaClient")
    def test_init_authentication_failure(self, mock_client_class):
        """Test initialization fails on authentication error."""
        mock_client_class.side_effect = Exception("Authentication failed")
        
        with pytest.raises(ValueError, match="authentication failed"):
            ThetaDataProvider()


class TestGetStockPrice:
    """Test get_stock_price method."""
    
    @pytest.fixture
    def provider(self):
        """Create a provider with mocked client."""
        with patch.dict("os.environ", {"THETADATA_USERNAME": "test_user", "THETADATA_PASSWORD": "test_pass"}):
            with patch("app.core.market_data.thetadata_provider.ThetaClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                provider = ThetaDataProvider()
                provider.client = mock_client
                yield provider
    
    def test_get_stock_price_success(self, provider):
        """Test successful price fetch."""
        provider.client.get_last_price.return_value = 150.50
        
        price = provider.get_stock_price("AAPL")
        
        assert price == 150.50
        provider.client.get_last_price.assert_called_once_with("AAPL")
    
    def test_get_stock_price_cached(self, provider):
        """Test price is cached."""
        provider.client.get_last_price.return_value = 150.50
        
        # First call
        price1 = provider.get_stock_price("AAPL")
        assert price1 == 150.50
        
        # Second call should use cache
        price2 = provider.get_stock_price("AAPL")
        assert price2 == 150.50
        # Should only be called once
        assert provider.client.get_last_price.call_count == 1
    
    def test_get_stock_price_invalid(self, provider):
        """Test price fetch with invalid data."""
        provider.client.get_last_price.return_value = None
        
        with pytest.raises(ValueError, match="Invalid price"):
            provider.get_stock_price("AAPL")
    
    def test_get_stock_price_error(self, provider):
        """Test price fetch with API error."""
        provider.client.get_last_price.side_effect = Exception("API error")
        
        with pytest.raises(ValueError, match="Failed to fetch price"):
            provider.get_stock_price("AAPL")


class TestGetEMA:
    """Test get_ema method."""
    
    @pytest.fixture
    def provider(self):
        """Create a provider with mocked client."""
        with patch.dict("os.environ", {"THETADATA_USERNAME": "test_user", "THETADATA_PASSWORD": "test_pass"}):
            with patch("app.core.market_data.thetadata_provider.ThetaClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                provider = ThetaDataProvider()
                provider.client = mock_client
                yield provider
    
    def test_get_ema_success(self, provider):
        """Test successful EMA calculation."""
        # Mock historical bars
        mock_bars = [
            {"date": date.today() - timedelta(days=i), "close": 100.0 + i * 0.5}
            for i in range(100, 0, -1)
        ]
        provider.client.get_historical_bars.return_value = mock_bars
        
        ema = provider.get_ema("AAPL", 50)
        
        assert isinstance(ema, float)
        assert ema > 0
        provider.client.get_historical_bars.assert_called_once()
    
    def test_get_ema_insufficient_data(self, provider):
        """Test EMA calculation with insufficient data."""
        provider.client.get_historical_bars.return_value = [{"date": date.today(), "close": 100.0}]
        
        with pytest.raises(ValueError, match="Insufficient data"):
            provider.get_ema("AAPL", 50)
    
    def test_get_ema_cached(self, provider):
        """Test EMA is cached."""
        mock_bars = [
            {"date": date.today() - timedelta(days=i), "close": 100.0 + i * 0.5}
            for i in range(100, 0, -1)
        ]
        provider.client.get_historical_bars.return_value = mock_bars
        
        # First call
        ema1 = provider.get_ema("AAPL", 50)
        
        # Second call should use cache
        ema2 = provider.get_ema("AAPL", 50)
        assert ema1 == ema2
        # Should only be called once
        assert provider.client.get_historical_bars.call_count == 1


class TestGetOptionsChain:
    """Test get_options_chain method."""
    
    @pytest.fixture
    def provider(self):
        """Create a provider with mocked client."""
        with patch.dict("os.environ", {"THETADATA_USERNAME": "test_user", "THETADATA_PASSWORD": "test_pass"}):
            with patch("app.core.market_data.thetadata_provider.ThetaClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                provider = ThetaDataProvider()
                provider.client = mock_client
                yield provider
    
    def test_get_options_chain_success(self, provider):
        """Test successful options chain fetch."""
        mock_chain = [
            {
                "strike": 150.0,
                "expiry": "2026-02-21",
                "type": "PUT",
                "bid": 2.50,
                "ask": 2.60,
                "delta": -0.25,
                "gamma": 0.01,
                "theta": -0.05,
                "vega": 0.10,
                "iv": 0.20,
                "open_interest": 1000,
                "volume": 500,
            }
        ]
        provider.client.get_options_chain.return_value = mock_chain
        
        chain = provider.get_options_chain("AAPL")
        
        assert len(chain) == 1
        assert isinstance(chain[0], OptionContract)
        assert chain[0].symbol == "AAPL"
        assert chain[0].strike == 150.0
        assert chain[0].option_type == "PUT"
        assert chain[0].mid == 2.55  # (2.50 + 2.60) / 2
    
    def test_get_options_chain_empty(self, provider):
        """Test options chain with no data."""
        provider.client.get_options_chain.return_value = []
        
        chain = provider.get_options_chain("AAPL")
        
        assert chain == []
    
    def test_get_options_chain_with_expiry(self, provider):
        """Test options chain with specific expiry."""
        mock_chain = [
            {
                "strike": 150.0,
                "expiry": "2026-02-21",
                "type": "PUT",
                "bid": 2.50,
                "ask": 2.60,
                "delta": -0.25,
            }
        ]
        provider.client.get_options_chain.return_value = mock_chain
        
        chain = provider.get_options_chain("AAPL", expiry="2026-02-21")
        
        assert len(chain) == 1
        provider.client.get_options_chain.assert_called_once_with(
            symbol="AAPL",
            expiry="2026-02-21",
        )
    
    def test_get_options_chain_cached(self, provider):
        """Test options chain is cached."""
        mock_chain = [
            {
                "strike": 150.0,
                "expiry": "2026-02-21",
                "type": "PUT",
                "bid": 2.50,
                "ask": 2.60,
                "delta": -0.25,
            }
        ]
        provider.client.get_options_chain.return_value = mock_chain
        
        # First call
        chain1 = provider.get_options_chain("AAPL")
        
        # Second call should use cache
        chain2 = provider.get_options_chain("AAPL")
        assert len(chain1) == len(chain2)
        # Should only be called once
        assert provider.client.get_options_chain.call_count == 1


class TestGetOptionMidPrice:
    """Test get_option_mid_price method."""
    
    @pytest.fixture
    def provider(self):
        """Create a provider with mocked client."""
        with patch.dict("os.environ", {"THETADATA_USERNAME": "test_user", "THETADATA_PASSWORD": "test_pass"}):
            with patch("app.core.market_data.thetadata_provider.ThetaClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                provider = ThetaDataProvider()
                provider.client = mock_client
                yield provider
    
    def test_get_option_mid_price_success(self, provider):
        """Test successful mid price fetch."""
        mock_chain = [
            {
                "strike": 150.0,
                "expiry": "2026-02-21",
                "type": "PUT",
                "bid": 2.50,
                "ask": 2.60,
                "delta": -0.25,
            }
        ]
        provider.client.get_options_chain.return_value = mock_chain
        
        mid_price = provider.get_option_mid_price("AAPL", 150.0, "2026-02-21", "PUT")
        
        assert mid_price == 2.55  # (2.50 + 2.60) / 2
    
    def test_get_option_mid_price_not_found(self, provider):
        """Test mid price fetch with contract not found."""
        provider.client.get_options_chain.return_value = []
        
        with pytest.raises(ValueError, match="Option contract not found"):
            provider.get_option_mid_price("AAPL", 150.0, "2026-02-21", "PUT")


class TestGetDTE:
    """Test get_dte method."""
    
    @pytest.fixture
    def provider(self):
        """Create a provider with mocked client."""
        with patch.dict("os.environ", {"THETADATA_USERNAME": "test_user", "THETADATA_PASSWORD": "test_pass"}):
            with patch("app.core.market_data.thetadata_provider.ThetaClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                provider = ThetaDataProvider()
                provider.client = mock_client
                yield provider
    
    def test_get_dte_future(self, provider):
        """Test DTE calculation for future expiry."""
        future_date = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        dte = provider.get_dte(future_date)
        
        assert dte == 30
    
    def test_get_dte_expired(self, provider):
        """Test DTE calculation for expired contract."""
        past_date = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        dte = provider.get_dte(past_date)
        
        assert dte == 0
    
    def test_get_dte_invalid_format(self, provider):
        """Test DTE calculation with invalid format."""
        with pytest.raises(ValueError, match="Invalid expiry format"):
            provider.get_dte("2026-13-45")


class TestGetDaily:
    """Test get_daily method (backward compatibility)."""
    
    @pytest.fixture
    def provider(self):
        """Create a provider with mocked client."""
        with patch.dict("os.environ", {"THETADATA_USERNAME": "test_user", "THETADATA_PASSWORD": "test_pass"}):
            with patch("app.core.market_data.thetadata_provider.ThetaClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                provider = ThetaDataProvider()
                provider.client = mock_client
                yield provider
    
    def test_get_daily_success(self, provider):
        """Test successful daily bars fetch."""
        import pandas as pd
        
        mock_bars = [
            {
                "date": date.today() - timedelta(days=i),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000000,
            }
            for i in range(10, 0, -1)
        ]
        provider.client.get_historical_bars.return_value = mock_bars
        
        df = provider.get_daily("AAPL", lookback=10)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 10
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
        assert df["date"].dtype == "datetime64[ns]"
    
    def test_get_daily_empty(self, provider):
        """Test daily bars fetch with no data."""
        provider.client.get_historical_bars.return_value = []
        
        with pytest.raises(ValueError, match="No historical data"):
            provider.get_daily("AAPL")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
