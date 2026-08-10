# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
from app.core.universe.screener_v3_r55 import screen_universe_v3


def test_screener_v3_no_retune():
    out = screen_universe_v3(
        [
            {"symbol": "NVDA", "liquidity_rank": 10, "has_options": True},
            {"symbol": "XYZ", "liquidity_rank": 1, "has_options": False},
        ],
        min_liquidity_rank=5,
        require_options=True,
    )
    assert out["threshold_retune"] is False
    by = {r["symbol"]: r for r in out["rows"]}
    assert by["NVDA"]["include"] is True
    assert by["XYZ"]["include"] is False
