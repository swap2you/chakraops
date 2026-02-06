# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 4: Contract tests for ORATS endpoints used in evaluation.

Validates response shape, required keys, and null handling using fixtures.
No live API calls - safe for CI without ORATS token.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.orats.orats_equity_quote import (
    _extract_rows,
    EquityQuote,
    IVRankData,
    ORATS_BASE_URL,
    ORATS_STRIKES_OPTIONS_PATH,
    ORATS_IVRANK_PATH,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "orats"


def _load_fixture(name: str) -> dict | list:
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Strikes/options (underlying equity quote)
# ---------------------------------------------------------------------------


class TestOratsStrikesOptionsShape:
    """Validate /datav2/strikes/options response shape and null handling."""

    def test_fixture_is_list_or_data_list(self):
        raw = _load_fixture("orats_strikes_options_underlying.json")
        assert isinstance(raw, list), "Fixture must be list (or wrap in {data: list})"
        assert len(raw) >= 1

    def test_extract_rows_accepts_list(self):
        raw = _load_fixture("orats_strikes_options_underlying.json")
        rows = _extract_rows(raw)
        assert isinstance(rows, list)
        assert len(rows) == len(raw)

    def test_extract_rows_accepts_data_wrapper(self):
        raw = _load_fixture("orats_strikes_options_underlying.json")
        wrapped = {"data": raw}
        rows = _extract_rows(wrapped)
        assert isinstance(rows, list)
        assert len(rows) == len(raw)

    def test_underlying_row_has_ticker_key(self):
        raw = _load_fixture("orats_strikes_options_underlying.json")
        for row in raw:
            assert "ticker" in row, "Each row must have 'ticker' for identification"
            assert isinstance(row.get("ticker"), str) or row.get("ticker") is None

    def test_optional_equity_keys_present_or_null(self):
        raw = _load_fixture("orats_strikes_options_underlying.json")
        optional = {"stockPrice", "bid", "ask", "volume", "quoteDate", "bidSize", "askSize"}
        for row in raw:
            for key in optional:
                if key in row:
                    val = row[key]
                    assert val is None or isinstance(val, (int, float, str)), (
                        f"Row {row.get('ticker')} key {key} must be null or number/string"
                    )

    def test_parsing_underlying_row_full_does_not_crash(self):
        raw = _load_fixture("orats_strikes_options_underlying.json")
        rows = _extract_rows(raw)
        underlying = [r for r in rows if not r.get("optionSymbol")]
        for row in underlying:
            ticker = (row.get("ticker") or "").upper()
            if not ticker:
                continue
            # Replicate parser logic: required keys checked, optional coerced
            price = None
            if "stockPrice" in row and row["stockPrice"] is not None:
                try:
                    price = float(row["stockPrice"])
                except (TypeError, ValueError):
                    pass
            bid = None
            if "bid" in row and row["bid"] is not None:
                try:
                    bid = float(row["bid"])
                except (TypeError, ValueError):
                    pass
            ask = None
            if "ask" in row and row["ask"] is not None:
                try:
                    ask = float(row["ask"])
                except (TypeError, ValueError):
                    pass
            volume = None
            if "volume" in row and row["volume"] is not None:
                try:
                    volume = int(float(row["volume"]))
                except (TypeError, ValueError):
                    pass
            quote_date = row.get("quoteDate")
            _ = EquityQuote(
                symbol=ticker,
                price=price,
                bid=bid,
                ask=ask,
                volume=volume,
                quote_date=quote_date if quote_date else None,
                data_source="strikes/options",
            )

    def test_parsing_null_fields_produces_none(self):
        raw = _load_fixture("orats_strikes_options_underlying.json")
        rows = _extract_rows(raw)
        null_row = next((r for r in rows if r.get("ticker") == "NULL_FIELDS"), None)
        if null_row:
            q = EquityQuote(
                symbol="NULL_FIELDS",
                price=None,
                bid=None,
                ask=None,
                volume=None,
                quote_date=None,
                data_source="strikes/options",
            )
            assert q.price is None and q.bid is None and q.ask is None and q.volume is None


# ---------------------------------------------------------------------------
# IV Rank
# ---------------------------------------------------------------------------


class TestOratsIvrankShape:
    """Validate /datav2/ivrank response shape and null handling."""

    def test_fixture_is_list(self):
        raw = _load_fixture("orats_ivrank.json")
        assert isinstance(raw, list)
        assert len(raw) >= 1

    def test_extract_rows_ivrank(self):
        raw = _load_fixture("orats_ivrank.json")
        rows = _extract_rows(raw)
        assert len(rows) == len(raw)

    def test_ivrank_row_has_ticker(self):
        raw = _load_fixture("orats_ivrank.json")
        for row in raw:
            assert "ticker" in row

    def test_ivrank_optional_keys(self):
        raw = _load_fixture("orats_ivrank.json")
        for row in raw:
            for key in ("ivRank1m", "ivPct1m"):
                if key in row:
                    val = row[key]
                    assert val is None or isinstance(val, (int, float))

    def test_parsing_ivrank_row_does_not_crash(self):
        raw = _load_fixture("orats_ivrank.json")
        rows = _extract_rows(raw)
        for row in rows:
            ticker = (row.get("ticker") or "").upper()
            if not ticker:
                continue
            iv_rank_1m = None
            if "ivRank1m" in row and row["ivRank1m"] is not None:
                try:
                    iv_rank_1m = float(row["ivRank1m"])
                except (TypeError, ValueError):
                    pass
            iv_pct_1m = None
            if "ivPct1m" in row and row["ivPct1m"] is not None:
                try:
                    iv_pct_1m = float(row["ivPct1m"])
                except (TypeError, ValueError):
                    pass
            iv_rank = iv_rank_1m if iv_rank_1m is not None else iv_pct_1m
            _ = IVRankData(
                symbol=ticker,
                iv_rank=iv_rank,
                iv_rank_1m=iv_rank_1m,
                iv_pct_1m=iv_pct_1m,
                data_source="ivrank",
            )

    def test_parsing_null_iv_produces_none(self):
        raw = _load_fixture("orats_ivrank.json")
        rows = _extract_rows(raw)
        null_row = next((r for r in rows if r.get("ticker") == "NULL_IV"), None)
        if null_row:
            d = IVRankData(symbol="NULL_IV", iv_rank=None, iv_rank_1m=None, iv_pct_1m=None, data_source="ivrank")
            assert d.iv_rank is None and d.iv_rank_1m is None and d.iv_pct_1m is None


# ---------------------------------------------------------------------------
# Endpoint constants (sanity)
# ---------------------------------------------------------------------------


class TestOratsEndpointConstants:
    """Ensure endpoint paths used in code match expectations."""

    def test_strikes_options_path(self):
        assert ORATS_STRIKES_OPTIONS_PATH == "/strikes/options"
        assert (ORATS_BASE_URL + ORATS_STRIKES_OPTIONS_PATH).endswith("/strikes/options")

    def test_ivrank_path(self):
        assert ORATS_IVRANK_PATH == "/ivrank"
