# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8E: Data contract surface — instrument type, required fields, derived fields, ORATS facade, validator.

Single source of truth: implementation lives in app.core.symbols; this package
re-exports for callers that prefer app.core.data.* (per THESIS.md / DATA_CONTRACT).
ORATS: all consumers MUST use app.core.data.orats_client (not app.core.orats directly).
Validation: use app.core.data.contract_validator for equity snapshot validation.
"""

from app.core.data.instrument_type import (
    InstrumentType,
    classify_instrument,
    get_required_fields_for_instrument,
    get_optional_liquidity_fields_for_instrument,
    clear_instrument_cache,
    KNOWN_ETF_SYMBOLS,
)
from app.core.data.data_dependencies import (
    compute_required_missing,
    compute_optional_missing,
    compute_required_stale,
    dependency_status,
    get_data_as_of,
    compute_dependency_lists,
    all_missing_fields,
    REQUIRED_EVALUATION_FIELDS,
    REQUIRED_EVALUATION_FIELDS_EQUITY,
    REQUIRED_EVALUATION_FIELDS_ETF_INDEX,
    OPTIONAL_EVALUATION_FIELDS,
)
from app.core.data.derived_fields import (
    DerivedValues,
    derive_equity_fields,
    effective_bid,
    effective_ask,
    effective_mid,
)
from app.core.data.contract_validator import (
    ContractValidationResult,
    validate_equity_snapshot,
)

__all__ = [
    "InstrumentType",
    "classify_instrument",
    "get_required_fields_for_instrument",
    "get_optional_liquidity_fields_for_instrument",
    "clear_instrument_cache",
    "KNOWN_ETF_SYMBOLS",
    "compute_required_missing",
    "compute_optional_missing",
    "compute_required_stale",
    "dependency_status",
    "get_data_as_of",
    "compute_dependency_lists",
    "REQUIRED_EVALUATION_FIELDS",
    "REQUIRED_EVALUATION_FIELDS_EQUITY",
    "REQUIRED_EVALUATION_FIELDS_ETF_INDEX",
    "OPTIONAL_EVALUATION_FIELDS",
    "all_missing_fields",
    "DerivedValues",
    "derive_equity_fields",
    "effective_bid",
    "effective_ask",
    "effective_mid",
    "ContractValidationResult",
    "validate_equity_snapshot",
]
