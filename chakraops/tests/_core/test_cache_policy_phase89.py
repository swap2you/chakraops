# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.9: Cache policy — central TTL."""

from __future__ import annotations

import pytest

from app.core.data.cache_policy import get_ttl


def test_get_ttl_known_endpoint():
    """get_ttl returns correct TTL for known endpoints."""
    assert get_ttl("cores") == 60
    assert get_ttl("strikes") == 60
    assert get_ttl("quotes") == 60
    assert get_ttl("iv_rank") == 6 * 3600
    assert get_ttl("calendar") == 24 * 3600
    assert get_ttl("earnings") == 24 * 3600


def test_get_ttl_default():
    """get_ttl returns DEFAULT_TTL (60) for unknown endpoint."""
    assert get_ttl("unknown_endpoint") == 60
    assert get_ttl("") == 60
    assert get_ttl("IV_RANK") == 6 * 3600
