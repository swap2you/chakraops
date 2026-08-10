# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R40.1: ORATS live/strikes field_presence uses side-specific keys."""

from __future__ import annotations

from app.core.orats.orats_client import _live_strikes_field_presence


def test_realistic_live_strikes_row_field_presence_not_all_false() -> None:
    row = {
        "ticker": "SPY",
        "stockPrice": 450.12,
        "quoteDate": "2026-08-10T15:30:00Z",
        "callBidPrice": 1.25,
        "callAskPrice": 1.35,
        "putBidPrice": 0.90,
        "putAskPrice": 1.00,
        "callOpenInterest": 1200,
        "putOpenInterest": 800,
        # no callVolume/putVolume → volume n/a
        # no ivRank on strikes rows
    }
    fp = _live_strikes_field_presence(row)
    assert fp["price"] is True
    assert fp["quote_date"] is True
    assert fp["bid"] is True
    assert fp["ask"] is True
    assert fp["open_interest"] is True
    assert fp["volume"] == "n/a"
    assert fp["iv_rank"] == "n/a_separate_endpoint"
    # Must not look like the old generic False-everywhere diagnosis
    bools = [v for v in (fp["price"], fp["bid"], fp["ask"], fp["open_interest"]) if isinstance(v, bool)]
    assert any(bools)
    assert not all(v is False for v in bools)


def test_side_volume_marks_volume_true() -> None:
    row = {
        "stockPrice": 10.0,
        "quoteDate": "2026-08-10",
        "callBidPrice": 0.1,
        "callAskPrice": 0.2,
        "callVolume": 5,
        "callOpenInterest": 1,
    }
    fp = _live_strikes_field_presence(row)
    assert fp["volume"] is True
