# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS chain mode selection: LIVE only when market OPEN, else DELAYED.

- get_chain_source(): OPEN → LIVE; else → DELAYED (Stage-1, expirations, etc.).
- get_stage2_chain_source(): Always DELAYED (Phase 3 HOTFIX: LIVE strikes lack per-contract option_type).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.options.orats_chain_provider import OratsChainProvider, get_chain_provider
from app.market.market_hours import get_stage2_chain_source


def test_get_stage2_chain_source_always_delayed():
    """Stage-2 chain source is DELAYED regardless of market phase."""
    assert get_stage2_chain_source() == "DELAYED"
    with patch("app.market.market_hours.get_market_phase", return_value="OPEN"):
        # get_stage2_chain_source does not depend on market phase
        assert get_stage2_chain_source() == "DELAYED"
    with patch("app.market.market_hours.get_market_phase", return_value="POST"):
        assert get_stage2_chain_source() == "DELAYED"


def test_stage2_uses_delayed_provider_even_when_market_open():
    """
    Phase 3 HOTFIX: Stage-2 must use DELAYED chain even when market is OPEN.
    LIVE /datav2/live/strikes does not provide per-contract option_type → puts_seen=0.
    """
    with patch("app.market.market_hours.get_market_phase", return_value="OPEN"):
        with patch("app.market.market_hours.get_chain_source", return_value="LIVE"):
            # Default get_chain_provider would use LIVE when market open
            default_provider = get_chain_provider()
            assert getattr(default_provider, "_chain_source", None) == "LIVE"
        # Stage-2 provider must be DELAYED
        stage2_provider = get_chain_provider(chain_source=get_stage2_chain_source())
        assert getattr(stage2_provider, "_chain_source", None) == "DELAYED"


def test_chain_uses_delayed_endpoints_when_market_closed():
    """
    When get_market_phase() returns POST (market closed), the provider must choose
    DELAYED ( pipeline /datav2/strikes + /datav2/strikes/options ).
    """
    with patch("app.market.market_hours.get_chain_source", return_value="DELAYED"):
        provider = get_chain_provider()
    assert getattr(provider, "_chain_source", None) == "DELAYED"

    with patch("app.market.market_hours.get_market_phase", return_value="POST"):
        with patch("app.market.market_hours.get_chain_source", return_value="DELAYED"):
            provider2 = OratsChainProvider(chain_source=None)
    assert provider2._chain_source == "DELAYED"

    # Explicit DELAYED: get_expirations should call pipeline fetch_base_chain with chain_mode=DELAYED
    provider3 = OratsChainProvider(chain_source="DELAYED")
    assert provider3._chain_source == "DELAYED"
    with patch("app.core.options.orats_chain_pipeline.fetch_base_chain") as m_fetch:
        m_fetch.return_value = ([], None, None)
        provider3.get_expirations("SPY")
    m_fetch.assert_called_once()
    call_kw = m_fetch.call_args[1]
    assert call_kw.get("chain_mode") == "DELAYED"
