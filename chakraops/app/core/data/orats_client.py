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

# Core Data v2 — single authoritative per-ticker snapshot (Phase 8A–8C)
from app.core.orats.orats_core_client import (
    fetch_core_snapshot,
    fetch_hist_dailies,
    OratsCoreError,
)
from app.core.data.equity_snapshot import (
    EquitySnapshot,
    build_equity_snapshot_from_core,
)


def get_equity_snapshot_from_core(
    ticker: str,
    derive_avg_stock_volume_20d: bool = False,
    timeout_sec: float = 15.0,
) -> EquitySnapshot:
    """Build EquitySnapshot from /datav2/cores using app token. Single path for Universe/Ticker/Evaluation."""
    from app.core.config.orats_secrets import ORATS_API_TOKEN
    token = ORATS_API_TOKEN or ""
    return build_equity_snapshot_from_core(
        ticker,
        token,
        timeout_sec=timeout_sec,
        derive_avg_stock_volume_20d=derive_avg_stock_volume_20d,
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
    "fetch_core_snapshot",
    "fetch_hist_dailies",
    "OratsCoreError",
    "EquitySnapshot",
    "build_equity_snapshot_from_core",
    "get_equity_snapshot_from_core",
]
