# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.9: Central TTL policy — single source of truth for cache lifetimes.

All ORATS endpoint TTLs defined here. Used by cache_store and ORATS clients.
"""

from __future__ import annotations

CACHE_TTL_SECONDS = {
    "cores": 60,
    "strikes": 60,
    "quotes": 60,
    "iv_rank": 6 * 3600,
    "calendar": 24 * 3600,
    "earnings": 24 * 3600,
}

DEFAULT_TTL = 60


def get_ttl(endpoint_name: str) -> int:
    """Return TTL in seconds for endpoint. Default 60 if not found."""
    if not endpoint_name:
        return DEFAULT_TTL
    return CACHE_TTL_SECONDS.get(endpoint_name.strip().lower(), DEFAULT_TTL)
