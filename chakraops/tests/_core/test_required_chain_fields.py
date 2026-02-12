# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Tests for REQUIRED_CHAIN_FIELDS and required_fields_present logic (Phase 3.3.1).

required_fields_present is True iff at least one selected_candidate has all
REQUIRED_CHAIN_FIELDS (strike, expiration, bid, ask, delta, open_interest) non-null and numeric.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.models.data_quality import DataQuality, FieldValue
from app.core.options.chain_provider import OptionContract, OptionType, SelectedContract
from app.core.eval.staged_evaluator import (
    REQUIRED_CHAIN_FIELDS,
    _contract_has_all_required_chain_fields,
    _compute_required_chain_fields_from_candidates,
    build_eligibility_layers,
    Stage2Result,
    Stage1Result,
    StockVerdict,
)


def _make_contract_with_all_required_fields() -> OptionContract:
    """Build OptionContract with all REQUIRED_CHAIN_FIELDS valid and numeric."""
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


class TestRequiredChainFieldsConstant:
    """REQUIRED_CHAIN_FIELDS must match Wheel strategy."""

    def test_required_chain_fields_defined(self):
        assert REQUIRED_CHAIN_FIELDS == [
            "strike",
            "expiration",
            "bid",
            "ask",
            "delta",
            "open_interest",
        ]


class TestContractHasAllRequiredChainFields:
    """_contract_has_all_required_chain_fields returns True only when all fields are non-null and numeric."""

    def test_full_contract_returns_true_empty_missing(self):
        contract = _make_contract_with_all_required_fields()
        ok, missing = _contract_has_all_required_chain_fields(contract)
        assert ok is True
        assert missing == []

    def test_missing_bid_returns_false(self):
        contract = _make_contract_with_all_required_fields()
        contract.bid = FieldValue(None, DataQuality.MISSING, "not fetched", "bid")
        ok, missing = _contract_has_all_required_chain_fields(contract)
        assert ok is False
        assert "bid" in missing

    def test_missing_open_interest_returns_false(self):
        contract = _make_contract_with_all_required_fields()
        contract.open_interest = FieldValue(None, DataQuality.MISSING, "", "open_interest")
        ok, missing = _contract_has_all_required_chain_fields(contract)
        assert ok is False
        assert "open_interest" in missing


class TestComputeRequiredChainFieldsFromCandidates:
    """_compute_required_chain_fields_from_candidates: True iff at least one candidate has all fields."""

    def test_one_full_candidate_returns_true_empty_missing(self):
        contract = _make_contract_with_all_required_fields()
        sc = SelectedContract(
            contract=contract,
            selection_reason="delta=-0.25, DTE=45",
            meets_all_criteria=True,
            criteria_results={},
        )
        present, missing = _compute_required_chain_fields_from_candidates([sc], ["bid"])
        assert present is True
        assert missing == []

    def test_empty_candidates_returns_false_keeps_current_missing(self):
        present, missing = _compute_required_chain_fields_from_candidates([], ["bid", "ask"])
        assert present is False
        assert missing == ["bid", "ask"]


def test_required_chain_fields_present_true_for_spy():
    """
    When Stage2Result has at least one selected_candidate with all REQUIRED_CHAIN_FIELDS,
    contract_data.required_fields_present must be True (e.g. SPY live evaluation).
    """
    contract = _make_contract_with_all_required_fields()
    sc = SelectedContract(
        contract=contract,
        selection_reason="delta=-0.25, DTE=45, grade=B",
        meets_all_criteria=True,
        criteria_results={"dte_in_range": True, "liquidity_ok": True},
    )
    stage2 = Stage2Result(
        symbol="SPY",
        expirations_available=3,
        expirations_evaluated=3,
        contracts_evaluated=100,
        selected_contract=sc,
        selected_candidates=[sc],
        liquidity_ok=True,
        liquidity_reason="OK",
        chain_missing_fields=[],  # Set by _compute_required_chain_fields_from_candidates in real path
    )
    stage1 = Stage1Result(
        symbol="SPY",
        stock_verdict=StockVerdict.QUALIFIED,
        stock_verdict_reason="",
    )
    symbol_eligibility, contract_data, contract_eligibility = build_eligibility_layers(
        stage1, stage2, "2026-02-10T16:00:00Z", market_open=True
    )
    assert contract_data["required_fields_present"] is True, (
        "SPY (with full selected_candidate) must yield required_fields_present True"
    )
    assert contract_data["available"] is True
    assert "expiration_count" in contract_data
    assert "contract_count" in contract_data


def test_contract_unavailable_when_no_enriched_chain():
    """
    When no enriched chain exists (no selected_candidates or required_fields_present false),
    contract_data.available must be False, source NONE, contract_eligibility UNAVAILABLE.
    """
    stage1 = Stage1Result(
        symbol="SPY",
        stock_verdict=StockVerdict.QUALIFIED,
        stock_verdict_reason="",
    )
    # Case 1: stage2 with no selected_candidates (chain fetched but no contract passed)
    stage2_no_candidates = Stage2Result(
        symbol="SPY",
        expirations_available=3,
        expirations_evaluated=3,
        contracts_evaluated=100,
        selected_contract=None,
        selected_candidates=[],
        liquidity_ok=False,
        liquidity_reason="No contracts meeting criteria",
        chain_missing_fields=["open_interest"],
    )
    _, contract_data, contract_eligibility = build_eligibility_layers(
        stage1, stage2_no_candidates, "2026-02-10T16:00:00Z", market_open=False
    )
    assert contract_data["available"] is False
    assert contract_data["source"] == "NONE"
    assert contract_data["required_fields_present"] is False
    assert contract_eligibility["status"] == "UNAVAILABLE"
    assert contract_eligibility["reasons"] == []

    # Case 2: stage2 with selected_candidates but required_fields_present false (missing fields on selected)
    contract_missing_oi = _make_contract_with_all_required_fields()
    contract_missing_oi.open_interest = FieldValue(None, DataQuality.MISSING, "", "open_interest")
    sc = SelectedContract(
        contract=contract_missing_oi,
        selection_reason="delta=-0.25",
        meets_all_criteria=True,
        criteria_results={},
    )
    stage2_missing_fields = Stage2Result(
        symbol="SPY",
        expirations_available=3,
        expirations_evaluated=3,
        contracts_evaluated=100,
        selected_contract=sc,
        selected_candidates=[sc],
        liquidity_ok=True,
        liquidity_reason="OK",
        chain_missing_fields=["open_interest"],
    )
    _, contract_data2, contract_eligibility2 = build_eligibility_layers(
        stage1, stage2_missing_fields, "2026-02-10T16:00:00Z", market_open=True
    )
    assert contract_data2["available"] is False
    assert contract_data2["source"] == "NONE"
    assert contract_data2["required_fields_present"] is False
    assert contract_eligibility2["status"] == "UNAVAILABLE"
    assert contract_eligibility2["reasons"] == []
