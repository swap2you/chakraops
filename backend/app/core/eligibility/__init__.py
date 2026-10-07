# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Eligibility gate (runs before Stage-2)."""

from app.core.eligibility.eligibility_engine import run as run_eligibility

__all__ = ["run_eligibility"]
