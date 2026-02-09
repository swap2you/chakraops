# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS v2 endpoint manifest — single source of truth for all ORATS API paths.

All ORATS HTTP callers MUST import base URLs and paths from this module.
No duplicate endpoint definitions elsewhere.

Base URLs:
  - BASE_DATAV2: Delayed and equity/ivrank (strikes/options with underlying, ivrank)
  - BASE_LIVE: Live strikes/summaries (datav2/live)
"""

from __future__ import annotations

# Delayed Data API (equity quote, ivrank, strikes, strikes/options for OCC)
BASE_DATAV2 = "https://api.orats.io/datav2"
PATH_STRIKES = "/strikes"
PATH_STRIKES_OPTIONS = "/strikes/options"
PATH_IVRANK = "/ivrank"

# Live API paths (same base BASE_DATAV2; paths are /live/strikes, /live/summaries)
PATH_LIVE_STRIKES = "/live/strikes"
PATH_LIVE_SUMMARIES = "/live/summaries"
BASE_LIVE = "https://api.orats.io/datav2/live"  # for providers that use .../live only

# Full URL helpers (for logging; callers build URL from base + path)
def url_strikes_options(base: str = BASE_DATAV2) -> str:
    return f"{base.rstrip('/')}{PATH_STRIKES_OPTIONS}"

def url_ivrank(base: str = BASE_DATAV2) -> str:
    return f"{base.rstrip('/')}{PATH_IVRANK}"

def url_live_strikes(base: str = BASE_DATAV2) -> str:
    return f"{base.rstrip('/')}{PATH_LIVE_STRIKES}"

def url_live_summaries(base: str = BASE_DATAV2) -> str:
    return f"{base.rstrip('/')}{PATH_LIVE_SUMMARIES}"

__all__ = [
    "BASE_DATAV2",
    "BASE_LIVE",
    "PATH_STRIKES",
    "PATH_STRIKES_OPTIONS",
    "PATH_IVRANK",
    "PATH_LIVE_STRIKES",
    "PATH_LIVE_SUMMARIES",
    "url_strikes_options",
    "url_ivrank",
    "url_live_strikes",
    "url_live_summaries",
]
