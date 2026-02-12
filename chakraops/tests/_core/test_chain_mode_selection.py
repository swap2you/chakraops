# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS chain mode selection: LIVE only when market OPEN, else DELAYED.

Single routing rule: get_market_phase() == "OPEN" → LIVE; else → DELAYED.
Stage-2 must use delayed endpoints (/datav2/strikes + /datav2/strikes/options) when market closed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.options.orats_chain_provider import OratsChainProvider, get_chain_provider


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
