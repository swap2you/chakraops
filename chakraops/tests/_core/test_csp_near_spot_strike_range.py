# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Assert CSP strike selection never returns deep OTM (min strike >= spot * 0.80)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.core.options.orats_chain_pipeline import fetch_base_chain

MIN_OTM_STRIKE_PCT = 0.80


def _make_strikes_rows(exp_str: str, spot: float, strikes: list[float], dte: int = 37) -> list[dict]:
    return [
        {
            "expirDate": exp_str,
            "strike": s,
            "dte": dte,
            "stockPrice": spot,
        }
        for s in strikes
    ]


@patch("app.core.options.orats_chain_pipeline.requests.get")
def test_csp_no_deep_otm_strike_range(mock_get):
    """
    fetch_base_chain must only select OTM PUT strikes in [spot*0.80, spot).
    requested_put_strikes.min must be >= spot_used * MIN_OTM_STRIKE_PCT (no strike=5 when spot=186).
    """
    exp = date.today() + timedelta(days=37)
    exp_str = exp.isoformat()
    spot = 186.0
    # Strikes from 100 to 185 (below spot); 80% of 186 = 148.8, so valid range is 148.8..185
    strikes = list(range(100, 186))
    rows = _make_strikes_rows(exp_str, spot, strikes)
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = rows
    mock_get.return_value.text = ""

    contracts, underlying_price, error, _ = fetch_base_chain(
        "NVDA", dte_min=30, dte_max=45, chain_mode="DELAYED"
    )

    assert error is None
    assert underlying_price == spot
    assert len(contracts) > 0
    min_strike = min(c.strike for c in contracts)
    min_floor = spot * MIN_OTM_STRIKE_PCT
    assert min_strike >= min_floor, (
        f"CSP strike selection must not include deep OTM: min_strike={min_strike} < spot*{MIN_OTM_STRIKE_PCT}={min_floor}"
    )
    assert all(c.strike < spot for c in contracts), "All selected strikes must be below spot (OTM puts)"
