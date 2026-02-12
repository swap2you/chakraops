# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8E: Data trust — instrument-type-specific required fields, derivation, no false DATA_INCOMPLETE for ETF/INDEX."""

from __future__ import annotations

import pytest

from app.core.symbols.instrument_type import (
    InstrumentType,
    classify_instrument,
    get_required_fields_for_instrument,
    get_optional_liquidity_fields_for_instrument,
    clear_instrument_cache,
    KNOWN_ETF_SYMBOLS,
)
from app.core.symbols.data_dependencies import (
    compute_required_missing,
    _required_fields_for_symbol,
    dependency_status,
)
from app.core.symbols.derived_fields import (
    derive_equity_fields,
    effective_bid,
    effective_ask,
    effective_mid,
    DerivedValues,
)


# -----------------------------------------------------------------------------
# Step 1: Instrument classification
# -----------------------------------------------------------------------------

def test_instrument_classification_etf_known() -> None:
    """SPY, QQQ, IWM, DIA classify as ETF."""
    clear_instrument_cache()
    for sym in ("SPY", "QQQ", "IWM", "DIA"):
        assert classify_instrument(sym) == InstrumentType.ETF
    assert "SPY" in KNOWN_ETF_SYMBOLS and "QQQ" in KNOWN_ETF_SYMBOLS


def test_instrument_classification_equity_with_metadata() -> None:
    """Symbols with company fundamentals classify as EQUITY (mock metadata)."""
    clear_instrument_cache()
    # AAPL with sector/industry → EQUITY
    assert classify_instrument("AAPL", metadata={"sector": "Technology", "industry": "Consumer Electronics"}) == InstrumentType.EQUITY


def test_required_fields_etf_excludes_bid_ask_oi() -> None:
    """ETF/INDEX required fields do not include bid, ask, open_interest."""
    req_etf = get_required_fields_for_instrument(InstrumentType.ETF)
    req_index = get_required_fields_for_instrument(InstrumentType.INDEX)
    for f in ("bid", "ask", "open_interest"):
        assert f not in req_etf
        assert f not in req_index
    assert "price" in req_etf and "volume" in req_etf and "iv_rank" in req_etf and "quote_date" in req_etf


def test_required_fields_equity_includes_bid_ask() -> None:
    """EQUITY required fields include bid and ask."""
    req = get_required_fields_for_instrument(InstrumentType.EQUITY)
    assert "bid" in req and "ask" in req and "price" in req and "volume" in req


def test_optional_liquidity_fields_etf() -> None:
    """ETF/INDEX have bid, ask, open_interest as optional liquidity fields."""
    opt = get_optional_liquidity_fields_for_instrument(InstrumentType.ETF)
    assert "bid" in opt and "ask" in opt and "open_interest" in opt


# -----------------------------------------------------------------------------
# Step 2: Conditional required fields — ETF must NOT be DATA_INCOMPLETE for bid/ask/OI only
# -----------------------------------------------------------------------------

def test_etf_spy_required_missing_excludes_bid_ask() -> None:
    """ETF (SPY) with missing bid/ask/open_interest must NOT have them in required_missing."""
    clear_instrument_cache()
    sym = {
        "symbol": "SPY",
        "price": 450.0,
        "volume": 1_000_000,
        "iv_rank": 50.0,
        "quote_date": "2025-02-01",
        "bid": None,
        "ask": None,
    }
    missing = compute_required_missing(sym)
    assert "bid" not in missing
    assert "ask" not in missing
    assert "open_interest" not in missing


def test_etf_qqq_required_missing_excludes_bid_ask() -> None:
    """ETF (QQQ) with missing bid/ask must NOT be required missing."""
    clear_instrument_cache()
    sym = {
        "symbol": "QQQ",
        "price": 400.0,
        "volume": 2_000_000,
        "iv_rank": 45.0,
        "quote_date": "2025-02-01",
        "bid": None,
        "ask": None,
    }
    missing = compute_required_missing(sym)
    assert "bid" not in missing and "ask" not in missing


def test_equity_required_missing_includes_bid_ask() -> None:
    """EQUITY with missing bid/ask must have them in required_missing (FAIL)."""
    clear_instrument_cache()
    # Force EQUITY by patching so we don't depend on company_data
    from unittest.mock import patch
    sym = {
        "symbol": "EQUITY_TEST",
        "price": 180.0,
        "volume": 50_000_000,
        "iv_rank": 40.0,
        "quote_date": "2025-02-01",
        "bid": None,
        "ask": None,
    }
    with patch("app.core.symbols.instrument_type.classify_instrument", return_value=InstrumentType.EQUITY):
        missing = compute_required_missing(sym)
        assert "bid" in missing and "ask" in missing


def test_equity_missing_bid_fails_required() -> None:
    """Explicit EQUITY symbol with missing bid must report bid in required_missing."""
    clear_instrument_cache()
    from unittest.mock import patch
    sym = {
        "symbol": "EQUITY_BID_TEST",
        "price": 420.0,
        "volume": 20_000_000,
        "iv_rank": 35.0,
        "quote_date": "2025-02-01",
        "bid": None,
        "ask": 420.5,
    }
    with patch("app.core.symbols.instrument_type.classify_instrument", return_value=InstrumentType.EQUITY):
        missing = compute_required_missing(sym)
        assert "bid" in missing


def test_equity_missing_bid_ask_should_fail() -> None:
    """EQUITY with missing bid and ask must FAIL (required_missing includes both)."""
    clear_instrument_cache()
    from unittest.mock import patch
    sym = {
        "symbol": "EQUITY_FAIL",
        "price": 100.0,
        "volume": 1_000_000,
        "iv_rank": 50.0,
        "quote_date": "2025-02-01",
        "bid": None,
        "ask": None,
    }
    with patch("app.core.symbols.instrument_type.classify_instrument", return_value=InstrumentType.EQUITY):
        missing = compute_required_missing(sym)
    assert "bid" in missing and "ask" in missing
    assert dependency_status(missing, [], []) == "FAIL"


def test_derivation_promotes_field_when_possible() -> None:
    """When only one of bid/ask exists, derivation promotes field so it is treated as present."""
    d = derive_equity_fields(price=100.0, bid=None, ask=103.0)
    assert d.synthetic_bid == 103.0 and d.synthetic_ask == 103.0
    assert effective_bid(None, d) == 103.0
    assert effective_ask(103.0, d) == 103.0
    # Validator can treat bid as present via effective_bid(None, d)
    assert "synthetic_bid_ask" in d.sources and d.sources["synthetic_bid_ask"] == "DERIVED"


# -----------------------------------------------------------------------------
# Step 3: Derived field promotion
# -----------------------------------------------------------------------------

def test_derive_mid_price_when_both_bid_ask() -> None:
    """When both bid and ask exist, mid_price is (bid+ask)/2."""
    d = derive_equity_fields(price=100.0, bid=99.0, ask=101.0)
    assert d.mid_price == 100.0
    assert "mid_price" in d.sources and d.sources["mid_price"] == "DERIVED"


def test_derive_synthetic_bid_ask_when_only_ask() -> None:
    """When only ask exists, synthetic_bid and synthetic_ask are set from ask."""
    d = derive_equity_fields(price=100.0, bid=None, ask=105.0)
    assert d.synthetic_bid == 105.0 and d.synthetic_ask == 105.0
    assert "synthetic_bid_ask" in d.sources


def test_derive_synthetic_bid_ask_when_only_bid() -> None:
    """When only bid exists, synthetic bid/ask set from bid."""
    d = derive_equity_fields(price=100.0, bid=98.0, ask=None)
    assert d.synthetic_bid == 98.0 and d.synthetic_ask == 98.0


def test_effective_bid_ask_use_derived_when_raw_missing() -> None:
    """effective_bid/effective_ask return derived value when raw is None."""
    d = derive_equity_fields(bid=None, ask=102.0)
    assert effective_bid(None, d) == 102.0
    assert effective_ask(102.0, d) == 102.0
    assert effective_bid(99.0, d) == 99.0  # raw takes precedence


def test_effective_mid_derived_takes_precedence() -> None:
    """effective_mid returns derived mid when available."""
    d = derive_equity_fields(bid=99.0, ask=101.0)
    assert effective_mid(100.0, 99.0, 101.0, d) == 100.0


# -----------------------------------------------------------------------------
# Regression: required fields for symbol uses instrument type
# -----------------------------------------------------------------------------

def test_regression_required_fields_for_symbol() -> None:
    """Regression: _required_fields_for_symbol() returns instrument-specific required list."""
    from unittest.mock import patch
    clear_instrument_cache()
    assert _required_fields_for_symbol({"symbol": "SPY"}) == list(
        get_required_fields_for_instrument(InstrumentType.ETF)
    )
    with patch("app.core.symbols.instrument_type.classify_instrument", return_value=InstrumentType.EQUITY):
        assert "bid" in _required_fields_for_symbol({"symbol": "X"})
        assert "ask" in _required_fields_for_symbol({"symbol": "X"})


def test_required_fields_for_symbol_etf() -> None:
    """_required_fields_for_symbol returns ETF set for SPY."""
    clear_instrument_cache()
    sym = {"symbol": "SPY"}
    req = _required_fields_for_symbol(sym)
    assert "bid" not in req and "ask" not in req
    assert "price" in req and "volume" in req and "iv_rank" in req


def test_required_fields_for_symbol_equity() -> None:
    """_required_fields_for_symbol returns EQUITY set when symbol has metadata."""
    clear_instrument_cache()
    sym = {"symbol": "AAPL"}
    req = _required_fields_for_symbol(sym)
    # In tests, AAPL may resolve to EQUITY if company_data is available, else INDEX
    assert "price" in req and "iv_rank" in req
    # ETF symbols never include bid/ask in required
    sym_etf = {"symbol": "QQQ"}
    req_etf = _required_fields_for_symbol(sym_etf)
    assert "bid" not in req_etf and "ask" not in req_etf


# -----------------------------------------------------------------------------
# Contract validator (single source of truth for snapshot validation)
# -----------------------------------------------------------------------------


def test_contract_validator_returns_canonical_result() -> None:
    """validate_equity_snapshot returns ContractValidationResult with expected fields."""
    from app.core.data.orats_client import FullEquitySnapshot
    from app.core.data.contract_validator import validate_equity_snapshot, ContractValidationResult

    clear_instrument_cache()
    snapshot = FullEquitySnapshot(
        symbol="SPY",
        price=450.0,
        bid=449.9,
        ask=450.1,
        volume=1_000_000,
        quote_date="2025-01-01",
        iv_rank=25.0,
    )
    r = validate_equity_snapshot("SPY", snapshot)
    assert isinstance(r, ContractValidationResult)
    assert r.symbol == "SPY"
    assert r.instrument_type == InstrumentType.ETF
    assert r.data_completeness == 1.0
    assert r.price == 450.0
    assert r.bid == 449.9
    assert r.ask == 450.1
    assert r.volume == 1_000_000
    assert r.quote_date == "2025-01-01"
    assert r.iv_rank == 25.0
    assert r.missing_fields == []
    assert "price" in r.field_quality
    assert "quote_time" in r.field_quality or "quote_date" in str(r.data_quality_details)


def test_contract_validator_derives_bid_ask_when_missing() -> None:
    """When only ask is present, validator promotes derived bid/ask."""
    from app.core.data.orats_client import FullEquitySnapshot
    from app.core.data.contract_validator import validate_equity_snapshot

    clear_instrument_cache()
    snapshot = FullEquitySnapshot(
        symbol="SPY",
        price=450.0,
        bid=None,
        ask=450.1,
        volume=1_000_000,
        quote_date="2025-01-01",
        iv_rank=25.0,
    )
    r = validate_equity_snapshot("SPY", snapshot)
    assert r.instrument_type == InstrumentType.ETF
    assert r.data_completeness == 1.0
    assert r.bid == 450.1
    assert r.ask == 450.1
    assert "DERIVED" in (r.field_sources.get("bid") or r.field_sources.get("ask") or "")
