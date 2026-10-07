# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Test that build_eligibility_layers correctly distinguishes:
- Chain available + selection FAIL (normal: filters rejected all contracts)
- Chain truly UNAVAILABLE (Stage-2 didn't run or fetch failed)
- Chain available + selection PASS
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.models.data_quality import DataQuality, FieldValue
from app.core.options.chain_provider import OptionContract, OptionType, SelectedContract
from app.core.eval.staged_evaluator import (
    build_eligibility_layers,
    Stage1Result,
    Stage2Result,
    StockVerdict,
)


def _make_contract() -> OptionContract:
    """OptionContract with all required fields."""
    return OptionContract(
        symbol="SPY",
        expiration=date(2026, 3, 20),
        strike=500.0,
        option_type=OptionType.PUT,
        bid=FieldValue(5.20, DataQuality.VALID, "", "bid"),
        ask=FieldValue(5.30, DataQuality.VALID, "", "ask"),
        mid=FieldValue(5.25, DataQuality.VALID, "", "mid"),
        last=FieldValue(5.25, DataQuality.VALID, "", "last"),
        open_interest=FieldValue(1200, DataQuality.VALID, "", "open_interest"),
        volume=FieldValue(100, DataQuality.VALID, "", "volume"),
        delta=FieldValue(-0.25, DataQuality.VALID, "", "delta"),
        gamma=FieldValue(0.02, DataQuality.VALID, "", "gamma"),
        theta=FieldValue(-0.05, DataQuality.VALID, "", "theta"),
        vega=FieldValue(0.10, DataQuality.VALID, "", "vega"),
        iv=FieldValue(0.18, DataQuality.VALID, "", "iv"),
        spread=FieldValue(0.10, DataQuality.VALID, "", "spread"),
        spread_pct=FieldValue(0.02, DataQuality.VALID, "", "spread_pct"),
        dte=45,
    )


class TestContractEligibilitySemantics:
    """Ensure available/FAIL/UNAVAILABLE/PASS semantics are correct."""

    def test_chain_fetched_but_no_candidates_is_FAIL_not_UNAVAILABLE(self):
        """
        Given: Stage-2 ran, returned contracts (contract_count > 0, puts_seen > 0),
               but all contracts were rejected by filters (selected_candidates empty).
        Expect:
            contract_data.available = True
            contract_eligibility.status = "FAIL"
            contract_eligibility.reasons contains the rejection reason
            contract_data.source != "NONE"
        """
        stage1 = Stage1Result(
            symbol="SPY",
            stock_verdict=StockVerdict.QUALIFIED,
            stock_verdict_reason="",
        )
        stage2 = Stage2Result(
            symbol="SPY",
            expirations_available=3,
            expirations_evaluated=3,
            contracts_evaluated=74,
            option_type_counts={"puts_seen": 37, "calls_seen": 37, "unknown_seen": 0},
            selected_candidates=[],
            contract_selection_reasons=["No contracts passed option liquidity gates (OI>=500, spread<=10%)"],
            liquidity_ok=False,
            liquidity_reason="No contracts meeting criteria",
            chain_missing_fields=[],
            required_fields_present=True,
            chain_source_used="DELAYED",
        )
        _, contract_data, contract_eligibility = build_eligibility_layers(
            stage1, stage2, "2026-02-10T16:00:00Z", market_open=False
        )
        assert contract_data["available"] is True
        assert contract_eligibility["status"] == "FAIL"
        assert "No contracts passed" in (contract_eligibility["reasons"][0] or "")
        assert contract_data["source"] != "NONE"
        assert contract_data["source"] == "DELAYED"

    def test_stage2_none_is_UNAVAILABLE(self):
        """
        Given: Stage-2 is None (didn't run at all).
        Expect:
            contract_data.available = False
            contract_eligibility.status = "UNAVAILABLE"
            contract_data.source = "NONE"
        """
        stage1 = Stage1Result(
            symbol="SPY",
            stock_verdict=StockVerdict.QUALIFIED,
            stock_verdict_reason="",
        )
        _, contract_data, contract_eligibility = build_eligibility_layers(
            stage1, None, "2026-02-10T16:00:00Z", market_open=True
        )
        assert contract_data["available"] is False
        assert contract_eligibility["status"] == "UNAVAILABLE"
        assert contract_data["source"] == "NONE"
        assert "Stage-2" in (contract_eligibility["reasons"][0] or "")

    def test_stage2_empty_chain_is_UNAVAILABLE(self):
        """
        Given: Stage-2 ran but returned 0 contracts (contract_count=0, empty chain).
        Expect:
            contract_data.available = False
            contract_eligibility.status = "UNAVAILABLE"
        """
        stage1 = Stage1Result(
            symbol="SPY",
            stock_verdict=StockVerdict.QUALIFIED,
            stock_verdict_reason="",
        )
        stage2 = Stage2Result(
            symbol="SPY",
            expirations_available=0,
            expirations_evaluated=0,
            contracts_evaluated=0,
            selected_candidates=[],
            liquidity_ok=False,
        )
        _, contract_data, contract_eligibility = build_eligibility_layers(
            stage1, stage2, "2026-02-10T16:00:00Z", market_open=False
        )
        assert contract_data["available"] is False
        assert contract_eligibility["status"] == "UNAVAILABLE"

    def test_stage2_with_selected_candidate_is_PASS(self):
        """
        Given: Stage-2 ran, returned contracts, and at least one candidate passed filters.
        Expect:
            contract_data.available = True
            contract_eligibility.status = "PASS"
            contract_data.source in ("LIVE", "DELAYED")
        """
        stage1 = Stage1Result(
            symbol="SPY",
            stock_verdict=StockVerdict.QUALIFIED,
            stock_verdict_reason="",
        )
        contract = _make_contract()
        sc = SelectedContract(
            contract=contract,
            selection_reason="delta=-0.25, DTE=45",
            meets_all_criteria=True,
            criteria_results={},
        )
        stage2 = Stage2Result(
            symbol="SPY",
            expirations_available=3,
            expirations_evaluated=3,
            contracts_evaluated=74,
            selected_contract=sc,
            selected_candidates=[sc],
            liquidity_ok=True,
            liquidity_reason="OK",
            chain_missing_fields=[],
            required_fields_present=True,
            chain_source_used="DELAYED",
        )
        _, contract_data, contract_eligibility = build_eligibility_layers(
            stage1, stage2, "2026-02-10T16:00:00Z", market_open=True
        )
        assert contract_data["available"] is True
        assert contract_eligibility["status"] == "PASS"
        assert contract_data["source"] == "DELAYED"
