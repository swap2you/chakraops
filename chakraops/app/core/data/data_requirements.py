# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Single authoritative DATA_REQUIREMENTS contract for ORATS data integration.

All UI, evaluation, and diagnostics MUST comply. See docs/DATA_REQUIREMENTS.md.
"""

from __future__ import annotations

from typing import Tuple

# -----------------------------------------------------------------------------
# Equity quote: ONLY delayed /strikes/options (underlying tickers)
# -----------------------------------------------------------------------------
EQUITY_QUOTE_SOURCE = "delayed_strikes_options"
EQUITY_QUOTE_ENDPOINT = "/datav2/strikes/options"
IV_RANK_ENDPOINT = "/datav2/ivrank"

# Live endpoints must NEVER be used for equity bid/ask/volume or iv_rank
LIVE_PATHS_FORBIDDEN_FOR_EQUITY = ("/datav2/live/", "/live/")

# -----------------------------------------------------------------------------
# Required fields for Stage-1 (all must be present and not stale → else BLOCK)
# -----------------------------------------------------------------------------
REQUIRED_STAGE1_FIELDS: Tuple[str, ...] = (
    "price",
    "bid",
    "ask",
    "volume",
    "quote_date",
    "iv_rank",
)

# -----------------------------------------------------------------------------
# Volume metrics: ONLY these two. No field named avg_volume (does not exist in ORATS).
# -----------------------------------------------------------------------------
# From /datav2/cores: avgOptVolu20d → avg_option_volume_20d (average options volume)
# Derived from /datav2/hist/dailies: stockVolume → mean of last N days → avg_stock_volume_Nd
VOLUME_METRICS_ALLOWED: Tuple[str, ...] = (
    "avg_option_volume_20d",   # ORATS cores: avgOptVolu20d
    "avg_stock_volume_20d",   # Derived: hist/dailies stockVolume, mean last 20
)

# Forbidden: must not appear in contract or as required/optional field name
FORBIDDEN_FIELD_NAMES: Tuple[str, ...] = ("avg_volume",)

# -----------------------------------------------------------------------------
# Stage-1 is a HARD GATE: missing or stale → BLOCK. No WARN + PASS.
# -----------------------------------------------------------------------------
STAGE1_STALE_TRADING_DAYS = 1  # > this many trading days stale → BLOCK

# -----------------------------------------------------------------------------
# Core data: /datav2/cores — GET ...?ticker=XXX&fields=ticker,stkVolu,avgOptVolu20d
# -----------------------------------------------------------------------------
CORES_VOLUME_FIELDS: Tuple[str, ...] = ("ticker", "stkVolu", "avgOptVolu20d")

# -----------------------------------------------------------------------------
# Historical: /datav2/hist/dailies — GET ...?ticker=XXX&fields=tradeDate,stockVolume
# Last N rows (default 20); avg_stock_volume_20d = mean(stockVolume).
# -----------------------------------------------------------------------------
HIST_DAILIES_FIELDS: Tuple[str, ...] = ("tradeDate", "stockVolume")
HIST_DAILIES_STOCK_VOLUME_FIELD = "stockVolume"
HIST_DAILIES_LOOKBACK_DAYS = 20
