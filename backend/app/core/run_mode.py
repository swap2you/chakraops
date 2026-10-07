# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Run mode for live discipline (Phase 6.1).

DRY_RUN: development/testing; config freeze not enforced.
PAPER_LIVE: paper trading; config freeze enforced.
LIVE: live (execution still manual); config freeze enforced.
"""

from __future__ import annotations

from enum import Enum


class RunMode(str, Enum):
    """Explicit run mode for the pipeline."""

    DRY_RUN = "DRY_RUN"
    PAPER_LIVE = "PAPER_LIVE"
    LIVE = "LIVE"


__all__ = ["RunMode"]
