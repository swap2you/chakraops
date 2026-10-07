# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Data dependencies: required/optional/stale by instrument type (Phase 8E).

Re-exports from app.core.symbols.data_dependencies — single implementation.
get_required_fields_for_instrument lives in instrument_type; use app.core.data.instrument_type.
"""

from app.core.symbols.data_dependencies import (
    REQUIRED_EVALUATION_FIELDS,
    REQUIRED_EVALUATION_FIELDS_EQUITY,
    REQUIRED_EVALUATION_FIELDS_ETF_INDEX,
    OPTIONAL_EVALUATION_FIELDS,
    STALENESS_TRADING_DAYS,
    compute_required_missing,
    compute_optional_missing,
    compute_required_stale,
    get_data_as_of,
    compute_dependency_lists,
    dependency_status,
    all_missing_fields,
)

__all__ = [
    "REQUIRED_EVALUATION_FIELDS",
    "REQUIRED_EVALUATION_FIELDS_EQUITY",
    "REQUIRED_EVALUATION_FIELDS_ETF_INDEX",
    "OPTIONAL_EVALUATION_FIELDS",
    "STALENESS_TRADING_DAYS",
    "compute_required_missing",
    "compute_optional_missing",
    "compute_required_stale",
    "get_data_as_of",
    "compute_dependency_lists",
    "dependency_status",
    "all_missing_fields",
]
