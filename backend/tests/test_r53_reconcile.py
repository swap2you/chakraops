# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R53 reconcile classification tests."""

from __future__ import annotations

from app.core.broker.reconcile_r53 import classify_holding, reconcile_manual_vs_broker


def test_classify_match_and_mismatches():
    assert classify_holding(symbol="NVDA", manual_qty=300, broker_qty=300) == "MATCH"
    assert classify_holding(symbol="SMCI", manual_qty=400, broker_qty=425) == "QUANTITY_MISMATCH"
    assert classify_holding(symbol="AMZN", manual_qty=None, broker_qty=25) == "BROKER_ONLY"
    assert classify_holding(symbol="XYZ", manual_qty=10, broker_qty=None) == "MANUAL_ONLY"
    assert (
        classify_holding(symbol="NVDA", manual_qty=300, broker_qty=300, manual_cost=100.0, broker_cost=157.0)
        == "COST_BASIS_MISMATCH"
    )


def test_reconcile_no_auto_mutation():
    out = reconcile_manual_vs_broker(
        [{"symbol": "NVDA", "shares": 300, "avg_cost": 150}],
        [{"symbol": "NVDA", "quantity": 300, "average_cost": 157.08}, {"symbol": "SMCI", "quantity": 425}],
    )
    assert out["auto_mutation"] is False
    assert out["trade_execution"] is False
    classes = {r["symbol"]: r["classification"] for r in out["rows"]}
    assert classes["NVDA"] == "COST_BASIS_MISMATCH"
    assert classes["SMCI"] == "BROKER_ONLY"
