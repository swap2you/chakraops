# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.3: Shares recommendation spine — eligibility, plan, sizing (request-time only)."""

from app.core.shares.shares_plan import (
    compute_shares_eligibility,
    build_shares_plan_r233,
)

__all__ = [
    "compute_shares_eligibility",
    "build_shares_plan_r233",
]
