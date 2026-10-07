# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Test that /strikes/options enrichment merge uses OCC option symbols so bid/ask/OI populate.

Given a base contract with opra_symbol 'AAPL230915C00175000' and an options row keyed by
the same OCC symbol, merge must populate bid/ask/open_interest and required_fields_present
must become True (when converted to OptionContract and checked).
"""

from datetime import date

import pytest

from app.core.options.orats_chain_pipeline import (
    BaseContract,
    merge_chain_and_liquidity,
    _normalize_occ_symbol,
    _build_opra_symbol_from_row,
)
from app.core.options.orats_chain_provider import OratsChainProvider
from app.core.options.chain_provider import OptionContract, OptionType
from app.core.eval.staged_evaluator import _contract_has_all_required_chain_fields


# OCC symbol (no space padding) for AAPL 2023-09-15 C 175
OCC_AAPL_230915_C_175 = "AAPL230915C00175000"


class TestOccSymbolNormalization:
    """Merge key must use normalized OCC (no spaces) to match BaseContract.opra_symbol."""

    def test_normalize_removes_spaces(self):
        assert _normalize_occ_symbol("SPY  260320P00691000") == "SPY260320P00691000"
        assert _normalize_occ_symbol(OCC_AAPL_230915_C_175) == OCC_AAPL_230915_C_175

    def test_build_opra_from_row_matches_base_format(self):
        row = {
            "ticker": "AAPL",
            "expirDate": "2023-09-15",
            "strike": 175.0,
            "putCall": "C",
        }
        built = _build_opra_symbol_from_row(row)
        assert built == OCC_AAPL_230915_C_175


class TestMergeKeyedByOccSymbol:
    """When enrichment_map is keyed by OCC symbol, merge populates bid/ask/OI."""

    def test_merge_populates_bid_ask_oi_and_required_fields_present(self):
        # Base contract: opra_symbol will be AAPL230915C00175000 (no padding)
        base = BaseContract(
            symbol="AAPL",
            expiration=date(2023, 9, 15),
            strike=175.0,
            option_type="CALL",
            dte=30,
            delta=0.5,
        )
        assert base.opra_symbol == OCC_AAPL_230915_C_175

        # Enrichment keyed by same OCC symbol (as API response would be after normalization)
        enrichment_map = {
            OCC_AAPL_230915_C_175: {
                "bid": 1.0,
                "ask": 1.05,
                "open_interest": 100,
                "delta": 0.5,
                "volume": 50,
            },
        }

        merged = merge_chain_and_liquidity(
            [base],
            enrichment_map,
            underlying_price=175.0,
            fetched_at="2023-09-01T12:00:00Z",
        )
        assert len(merged) == 1
        ec = merged[0]
        assert ec.bid == 1.0
        assert ec.ask == 1.05
        assert ec.open_interest == 100
        assert ec.opra_symbol == OCC_AAPL_230915_C_175

        # Convert to OptionContract and assert required chain fields pass
        provider = OratsChainProvider(chain_source="DELAYED")
        oc = provider._enriched_to_option_contract(ec, "AAPL")
        oc.compute_derived_fields()
        assert oc.option_symbol == OCC_AAPL_230915_C_175
        has_all, missing = _contract_has_all_required_chain_fields(oc)
        assert has_all is True, f"missing required fields: {missing}"
        assert not missing
