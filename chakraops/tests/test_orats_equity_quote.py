# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Unit tests for ORATS equity quote fetcher.

Tests:
1. Batching to groups of 10 tickers
2. Mapping of /strikes/options underlying rows -> EquityQuote fields
3. Mapping of /ivrank rows -> IVRankData fields
4. Correct missing_fields + data_sources when fields are absent
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, List, Any

from app.core.orats.orats_equity_quote import (
    EquityQuote,
    IVRankData,
    FullEquitySnapshot,
    EquityQuoteCache,
    _batch_tickers,
    fetch_equity_quotes_batch,
    fetch_iv_ranks_batch,
    fetch_full_equity_snapshots,
    reset_run_cache,
)


class TestBatching:
    """Test ticker batching logic."""
    
    def test_batch_tickers_small_set(self):
        """Test batching with fewer than 10 tickers."""
        tickers = ["AAPL", "MSFT", "GOOGL"]
        batches = _batch_tickers(tickers, batch_size=10)
        
        assert len(batches) == 1
        assert batches[0] == ["AAPL", "MSFT", "GOOGL"]
    
    def test_batch_tickers_exact_batch(self):
        """Test batching with exactly 10 tickers."""
        tickers = [f"SYM{i}" for i in range(10)]
        batches = _batch_tickers(tickers, batch_size=10)
        
        assert len(batches) == 1
        assert len(batches[0]) == 10
    
    def test_batch_tickers_multiple_batches(self):
        """Test batching with 25 tickers (should create 3 batches)."""
        tickers = [f"SYM{i}" for i in range(25)]
        batches = _batch_tickers(tickers, batch_size=10)
        
        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 5
    
    def test_batch_tickers_empty_list(self):
        """Test batching with empty list."""
        batches = _batch_tickers([], batch_size=10)
        assert batches == []


class TestEquityQuoteMapping:
    """Test mapping of ORATS /strikes/options underlying rows to EquityQuote."""
    
    def setup_method(self):
        """Reset cache before each test."""
        reset_run_cache()
    
    @patch("app.core.orats.orats_equity_quote.requests.get")
    @patch("app.core.orats.orats_equity_quote._get_orats_token")
    def test_maps_all_equity_fields(self, mock_token, mock_get):
        """Test that all equity fields are correctly mapped from ORATS response."""
        mock_token.return_value = "test_token"
        
        # Mock ORATS response with underlying row
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "ticker": "AAPL",
                    "stockPrice": 185.50,
                    "bid": 185.45,
                    "ask": 185.55,
                    "bidSize": 100,
                    "askSize": 150,
                    "volume": 45000000,
                    "quoteDate": "2026-02-03",
                }
            ]
        }
        mock_get.return_value = mock_response
        
        quotes = fetch_equity_quotes_batch(["AAPL"])
        
        assert "AAPL" in quotes
        quote = quotes["AAPL"]
        
        assert quote.symbol == "AAPL"
        assert quote.price == 185.50
        assert quote.bid == 185.45
        assert quote.ask == 185.55
        assert quote.volume == 45000000
        assert quote.bid_size == 100
        assert quote.ask_size == 150
        assert quote.quote_date == "2026-02-03"
        assert quote.data_source == "strikes/options"
        assert "stockPrice" in quote.raw_fields_present
        assert "bid" in quote.raw_fields_present
        assert "ask" in quote.raw_fields_present
        assert "volume" in quote.raw_fields_present
    
    @patch("app.core.orats.orats_equity_quote.requests.get")
    @patch("app.core.orats.orats_equity_quote._get_orats_token")
    def test_handles_missing_fields(self, mock_token, mock_get):
        """Test that missing fields are properly handled."""
        mock_token.return_value = "test_token"
        
        # Mock ORATS response with only stockPrice (no bid/ask/volume)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "ticker": "AAPL",
                    "stockPrice": 185.50,
                    # bid, ask, volume are missing
                }
            ]
        }
        mock_get.return_value = mock_response
        
        quotes = fetch_equity_quotes_batch(["AAPL"])
        
        assert "AAPL" in quotes
        quote = quotes["AAPL"]
        
        assert quote.price == 185.50
        assert quote.bid is None
        assert quote.ask is None
        assert quote.volume is None
        assert "stockPrice" in quote.raw_fields_present
        assert "bid" not in quote.raw_fields_present
    
    @patch("app.core.orats.orats_equity_quote.requests.get")
    @patch("app.core.orats.orats_equity_quote._get_orats_token")
    def test_handles_no_underlying_row(self, mock_token, mock_get):
        """Test that tickers with no underlying row get error entries."""
        mock_token.return_value = "test_token"
        
        # Mock ORATS response with empty data (no underlying row)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response
        
        quotes = fetch_equity_quotes_batch(["AAPL"])
        
        assert "AAPL" in quotes
        quote = quotes["AAPL"]
        
        assert quote.error is not None
        assert "No underlying row" in quote.error


class TestIVRankMapping:
    """Test mapping of ORATS /ivrank rows to IVRankData."""
    
    def setup_method(self):
        """Reset cache before each test."""
        reset_run_cache()
    
    @patch("app.core.orats.orats_equity_quote.requests.get")
    @patch("app.core.orats.orats_equity_quote._get_orats_token")
    def test_maps_ivrank1m(self, mock_token, mock_get):
        """Test that ivRank1m is correctly mapped."""
        mock_token.return_value = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "ticker": "AAPL",
                    "ivRank1m": 45.5,
                    "ivPct1m": 42.0,
                }
            ]
        }
        mock_get.return_value = mock_response
        
        iv_ranks = fetch_iv_ranks_batch(["AAPL"])
        
        assert "AAPL" in iv_ranks
        iv = iv_ranks["AAPL"]
        
        assert iv.symbol == "AAPL"
        # ivRank1m takes precedence
        assert iv.iv_rank == 45.5
        assert iv.iv_rank_1m == 45.5
        assert iv.iv_pct_1m == 42.0
        assert iv.data_source == "ivrank"
        assert "ivRank1m" in iv.raw_fields_present
    
    @patch("app.core.orats.orats_equity_quote.requests.get")
    @patch("app.core.orats.orats_equity_quote._get_orats_token")
    def test_falls_back_to_ivpct1m(self, mock_token, mock_get):
        """Test that ivPct1m is used when ivRank1m is not available."""
        mock_token.return_value = "test_token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "ticker": "AAPL",
                    # ivRank1m not present
                    "ivPct1m": 38.0,
                }
            ]
        }
        mock_get.return_value = mock_response
        
        iv_ranks = fetch_iv_ranks_batch(["AAPL"])
        
        assert "AAPL" in iv_ranks
        iv = iv_ranks["AAPL"]
        
        # Should fall back to ivPct1m
        assert iv.iv_rank == 38.0
        assert iv.iv_rank_1m is None
        assert iv.iv_pct_1m == 38.0


class TestFullEquitySnapshot:
    """Test combined equity quote + IV rank snapshots."""
    
    def setup_method(self):
        """Reset cache before each test."""
        reset_run_cache()
    
    @patch("app.core.orats.orats_equity_quote.fetch_iv_ranks_batch")
    @patch("app.core.orats.orats_equity_quote.fetch_equity_quotes_batch")
    def test_combines_quote_and_ivrank(self, mock_eq, mock_iv):
        """Test that full snapshot combines both equity quote and IV rank."""
        mock_eq.return_value = {
            "AAPL": EquityQuote(
                symbol="AAPL",
                price=185.50,
                bid=185.45,
                ask=185.55,
                volume=45000000,
                quote_date="2026-02-03",
                raw_fields_present=["stockPrice", "bid", "ask", "volume", "quoteDate"],
            )
        }
        mock_iv.return_value = {
            "AAPL": IVRankData(
                symbol="AAPL",
                iv_rank=45.5,
                raw_fields_present=["ivRank1m"],
            )
        }
        
        snapshots = fetch_full_equity_snapshots(["AAPL"])
        
        assert "AAPL" in snapshots
        snap = snapshots["AAPL"]
        
        # From equity quote
        assert snap.price == 185.50
        assert snap.bid == 185.45
        assert snap.ask == 185.55
        assert snap.volume == 45000000
        assert snap.quote_date == "2026-02-03"
        
        # From IV rank
        assert snap.iv_rank == 45.5
        
        # avg_volume is always None (not available from ORATS)
        assert snap.avg_volume is None
        assert "avg_volume" in snap.missing_fields
        assert "Not available from ORATS" in snap.missing_reasons["avg_volume"]
        
        # Data sources should track which endpoint provided each field
        assert snap.data_sources.get("price") == "strikes/options"
        assert snap.data_sources.get("bid") == "strikes/options"
        assert snap.data_sources.get("iv_rank") == "ivrank"
    
    @patch("app.core.orats.orats_equity_quote.fetch_iv_ranks_batch")
    @patch("app.core.orats.orats_equity_quote.fetch_equity_quotes_batch")
    def test_tracks_missing_fields_correctly(self, mock_eq, mock_iv):
        """Test that missing fields are correctly tracked with reasons."""
        mock_eq.return_value = {
            "AAPL": EquityQuote(
                symbol="AAPL",
                price=185.50,
                bid=None,  # Missing
                ask=None,  # Missing
                volume=None,  # Missing
                raw_fields_present=["stockPrice"],
            )
        }
        mock_iv.return_value = {
            "AAPL": IVRankData(
                symbol="AAPL",
                iv_rank=None,  # Missing
                error="No IV rank row returned by ORATS",
            )
        }
        
        snapshots = fetch_full_equity_snapshots(["AAPL"])
        snap = snapshots["AAPL"]
        
        # Check missing fields
        assert "bid" in snap.missing_fields
        assert "ask" in snap.missing_fields
        assert "volume" in snap.missing_fields
        assert "iv_rank" in snap.missing_fields
        assert "avg_volume" in snap.missing_fields  # Always missing
        
        # Price should NOT be missing
        assert "price" not in snap.missing_fields
        
        # Check data sources only has price
        assert "price" in snap.data_sources
        assert "bid" not in snap.data_sources


class TestCache:
    """Test caching behavior."""
    
    def setup_method(self):
        """Reset cache before each test."""
        reset_run_cache()
    
    def test_cache_stores_and_retrieves(self):
        """Test that cache correctly stores and retrieves quotes."""
        cache = EquityQuoteCache()
        
        quote = EquityQuote(symbol="AAPL", price=185.50)
        cache.set_equity_quote("AAPL", quote)
        
        retrieved = cache.get_equity_quote("AAPL")
        assert retrieved is not None
        assert retrieved.price == 185.50
    
    def test_cache_is_case_insensitive(self):
        """Test that cache lookup is case-insensitive."""
        cache = EquityQuoteCache()
        
        quote = EquityQuote(symbol="AAPL", price=185.50)
        cache.set_equity_quote("aapl", quote)
        
        retrieved = cache.get_equity_quote("AAPL")
        assert retrieved is not None
    
    def test_cache_batch_deduplication(self):
        """Test that fetched batches are tracked to prevent duplicates."""
        cache = EquityQuoteCache()
        
        # First call should return False (batch not fetched)
        assert cache.mark_batch_fetched("AAPL,MSFT") is False
        
        # Second call should return True (batch already fetched)
        assert cache.mark_batch_fetched("AAPL,MSFT") is True


class TestDataQuality:
    """Test data quality details and source tracking."""
    
    def setup_method(self):
        """Reset cache before each test."""
        reset_run_cache()
    
    @patch("app.core.orats.orats_equity_quote.fetch_iv_ranks_batch")
    @patch("app.core.orats.orats_equity_quote.fetch_equity_quotes_batch")
    def test_data_sources_populated_correctly(self, mock_eq, mock_iv):
        """Test that data_sources dict correctly tracks which endpoint provided each field."""
        mock_eq.return_value = {
            "AAPL": EquityQuote(
                symbol="AAPL",
                price=185.50,
                bid=185.45,
                ask=185.55,
                volume=45000000,
                quote_date="2026-02-03",
                raw_fields_present=["stockPrice", "bid", "ask", "volume", "quoteDate"],
            )
        }
        mock_iv.return_value = {
            "AAPL": IVRankData(
                symbol="AAPL",
                iv_rank=45.5,
                raw_fields_present=["ivRank1m"],
            )
        }
        
        snapshots = fetch_full_equity_snapshots(["AAPL"])
        snap = snapshots["AAPL"]
        
        # Verify data sources
        expected_sources = {
            "price": "strikes/options",
            "bid": "strikes/options",
            "ask": "strikes/options",
            "volume": "strikes/options",
            "quote_date": "strikes/options",
            "iv_rank": "ivrank",
        }
        
        for field, expected_source in expected_sources.items():
            assert snap.data_sources.get(field) == expected_source, f"Field {field} has wrong source"
    
    @patch("app.core.orats.orats_equity_quote.fetch_iv_ranks_batch")
    @patch("app.core.orats.orats_equity_quote.fetch_equity_quotes_batch")
    def test_raw_fields_present_combined(self, mock_eq, mock_iv):
        """Test that raw_fields_present combines fields from both endpoints."""
        mock_eq.return_value = {
            "AAPL": EquityQuote(
                symbol="AAPL",
                price=185.50,
                raw_fields_present=["stockPrice", "bid"],
            )
        }
        mock_iv.return_value = {
            "AAPL": IVRankData(
                symbol="AAPL",
                iv_rank=45.5,
                raw_fields_present=["ivRank1m", "ivPct1m"],
            )
        }
        
        snapshots = fetch_full_equity_snapshots(["AAPL"])
        snap = snapshots["AAPL"]
        
        # Should contain fields from both endpoints
        assert "stockPrice" in snap.raw_fields_present
        assert "bid" in snap.raw_fields_present
        assert "ivRank1m" in snap.raw_fields_present
        assert "ivPct1m" in snap.raw_fields_present
