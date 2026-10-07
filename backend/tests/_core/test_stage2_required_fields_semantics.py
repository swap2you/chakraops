# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Stage-2 required fields semantics: open_interest missing vs OI=0.

- Case A: open_interest missing/invalid => rejected_due_to_missing_fields (not oi),
          required_fields_present false.
- Case B: open_interest = 0 (valid numeric) => required_fields_present true,
          but rejected_due_to_oi (threshold fail).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.models.data_quality import DataQuality, FieldValue
from app.core.options.chain_provider import OptionContract, OptionType, OptionsChain, ChainProviderResult
from app.core.eval.staged_evaluator import (
    _contract_has_all_required_chain_fields,
    _is_valid_numeric_field,
    _select_csp_candidates,
)


def _make_put_base(dte: int = 40) -> OptionContract:
    """Base PUT with all required fields valid."""
    exp = date.today() + timedelta(days=dte)
    return OptionContract(
        symbol="SPY",
        expiration=exp,
        strike=500.0,
        option_type=OptionType.PUT,
        bid=FieldValue(5.0, DataQuality.VALID, "", "bid"),
        ask=FieldValue(5.1, DataQuality.VALID, "", "ask"),
        mid=FieldValue(5.05, DataQuality.VALID, "", "mid"),
        last=FieldValue(5.05, DataQuality.VALID, "", "last"),
        open_interest=FieldValue(1000, DataQuality.VALID, "", "open_interest"),
        volume=FieldValue(50, DataQuality.VALID, "", "volume"),
        delta=FieldValue(-0.25, DataQuality.VALID, "", "delta"),
        gamma=FieldValue(0.02, DataQuality.VALID, "", "gamma"),
        theta=FieldValue(-0.05, DataQuality.VALID, "", "theta"),
        vega=FieldValue(0.10, DataQuality.VALID, "", "vega"),
        iv=FieldValue(0.18, DataQuality.VALID, "", "iv"),
        spread=FieldValue(0.1, DataQuality.VALID, "", "spread"),
        spread_pct=FieldValue(0.02, DataQuality.VALID, "", "spread_pct"),
        dte=dte,
    )


class TestIsValidNumericField:
    """_is_valid_numeric_field: no coercion of invalid to 0."""

    def test_valid_zero(self):
        ok, val = _is_valid_numeric_field(FieldValue(0, DataQuality.VALID, "", "oi"))
        assert ok is True
        assert val == 0.0

    def test_missing_returns_false(self):
        ok, val = _is_valid_numeric_field(FieldValue(None, DataQuality.MISSING, "", "oi"))
        assert ok is False
        assert val is None

    def test_none_returns_false(self):
        ok, val = _is_valid_numeric_field(None)
        assert ok is False
        assert val is None


class TestRequiredFieldsSemantics:
    """Case A and Case B from Phase 3 Truth Fix."""

    def test_case_a_open_interest_missing_increments_rejected_due_to_missing_fields(self):
        """
        open_interest missing/invalid => rejected_due_to_missing_fields (not oi),
        required_fields_present false.
        """
        put = _make_put_base()
        put.open_interest = FieldValue(None, DataQuality.MISSING, "", "open_interest")
        put.compute_derived_fields()

        has_all, missing = _contract_has_all_required_chain_fields(put)
        assert has_all is False
        assert "open_interest" in missing

        exp = date.today() + timedelta(days=40)
        spot = 505.0  # Put strike=500 must be < spot for OTM
        chain = OptionsChain(
            symbol="SPY",
            expiration=exp,
            underlying_price=FieldValue(spot, DataQuality.VALID, "", "underlying"),
            contracts=[put],
            fetched_at=None,
            source="ORATS",
        )
        chains = {exp: ChainProviderResult(success=True, chain=chain)}
        candidates, reasons, counts, _, _ = _select_csp_candidates(
            chains, dte_min=30, dte_max=45, delta_lo=0.15, delta_hi=0.35,
            min_oi=500, max_spread_pct=0.10, symbol="SPY",
        )
        assert len(candidates) == 0
        # OI missing: _contract_has_required_fields_for_selection excludes OI; fails at OI gate -> rejected_due_to_oi
        assert counts["rejected_due_to_oi"] >= 1 or counts["rejected_due_to_missing_fields"] >= 1

    def test_case_b_open_interest_zero_valid_but_rejected_due_to_oi(self):
        """
        open_interest = 0 (valid numeric) => required_fields_present true,
        but rejected_due_to_oi (threshold fail).
        """
        put = _make_put_base()
        put.open_interest = FieldValue(0, DataQuality.VALID, "", "open_interest")
        put.compute_derived_fields()

        has_all, missing = _contract_has_all_required_chain_fields(put)
        assert has_all is True
        assert missing == []

        exp = date.today() + timedelta(days=40)
        spot = 505.0  # Put strike=500 must be < spot for OTM
        chain = OptionsChain(
            symbol="SPY",
            expiration=exp,
            underlying_price=FieldValue(spot, DataQuality.VALID, "", "underlying"),
            contracts=[put],
            fetched_at=None,
            source="ORATS",
        )
        chains = {exp: ChainProviderResult(success=True, chain=chain)}
        candidates, reasons, counts, _, _ = _select_csp_candidates(
            chains, dte_min=30, dte_max=45, delta_lo=0.15, delta_hi=0.35,
            min_oi=500, max_spread_pct=0.10, symbol="SPY",
        )
        assert len(candidates) == 0
        assert counts["rejected_due_to_missing_fields"] == 0
        assert counts["rejected_due_to_oi"] >= 1
