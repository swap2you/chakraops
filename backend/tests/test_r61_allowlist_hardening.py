# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R61: production read allowlist excludes order-review preview tools."""

from __future__ import annotations

import pytest

from app.core.broker.allowlist import (
    ROBINHOOD_READ_TOOL_ALLOWLIST,
    assert_tool_allowed,
)


@pytest.mark.parametrize("tool", ["review_equity_order", "review_option_order"])
def test_review_order_tools_not_on_production_allowlist(tool: str):
    assert tool not in ROBINHOOD_READ_TOOL_ALLOWLIST
    with pytest.raises(PermissionError):
        assert_tool_allowed(tool)


def test_core_portfolio_reads_still_allowed():
    for tool in ("get_accounts", "get_portfolio", "get_equity_positions", "get_option_positions"):
        assert_tool_allowed(tool)
