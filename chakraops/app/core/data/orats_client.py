# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Single ORATS client facade — the ONLY module callers must use to obtain ORATS data.

All fetch paths (equity snapshots, live strikes/summaries, probe) go through this module.
Implementation lives in app.core.orats; this module delegates and re-exports so there is
one canonical import for consumers.

UI, CLI, API, and nightly scripts MUST import from app.core.data.orats_client (or backend
APIs that use it). Do NOT import app.core.orats or app.data.orats_client from consumers.
"""

from __future__ import annotations

# Equity snapshots (Stage 1: strikes/options + ivrank)
from app.core.orats.orats_equity_quote import (
    fetch_full_equity_snapshots,
    reset_run_cache,
    OratsEquityQuoteError,
    FullEquitySnapshot,
    EquityQuoteCache,
    get_run_cache,
)

# Live endpoints (strikes, summaries, probe)
from app.core.orats.orats_client import (
    get_orats_live_strikes,
    get_orats_live_summaries,
    probe_orats_live,
    OratsUnavailableError,
    ORATS_BASE,
)

__all__ = [
    "fetch_full_equity_snapshots",
    "reset_run_cache",
    "get_run_cache",
    "OratsEquityQuoteError",
    "FullEquitySnapshot",
    "EquityQuoteCache",
    "get_orats_live_strikes",
    "get_orats_live_summaries",
    "probe_orats_live",
    "OratsUnavailableError",
    "ORATS_BASE",
]
