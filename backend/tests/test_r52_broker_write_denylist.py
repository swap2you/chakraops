# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52: every write/deny tool rejected; allowlisted reads accepted."""

from __future__ import annotations

import pytest

from app.core.broker.allowlist import (
    ROBINHOOD_READ_TOOL_ALLOWLIST,
    ROBINHOOD_WRITE_TOOL_DENYLIST,
    ToolClass,
    assert_tool_allowed,
    classify_tool,
)

# Live MCP discovery (Cursor user-robinhood-trading) — write surface must stay denied.
LIVE_WRITE_TOOLS = (
    "place_equity_order",
    "place_option_order",
    "cancel_equity_order",
    "cancel_option_order",
    "cancel_option_exercise",
    "exercise_option",
    "add_to_watchlist",
    "add_option_to_watchlist",
    "remove_from_watchlist",
    "remove_option_from_watchlist",
    "create_watchlist",
    "update_watchlist",
    "create_scan",
    "update_scan_config",
    "update_scan_filters",
    "run_scan",
    "follow_watchlist",
    "unfollow_watchlist",
)


@pytest.mark.parametrize("tool", LIVE_WRITE_TOOLS)
def test_write_tools_denied(tool: str):
    assert tool in ROBINHOOD_WRITE_TOOL_DENYLIST
    assert classify_tool(tool) is ToolClass.WRITE
    with pytest.raises(PermissionError):
        assert_tool_allowed(tool)


@pytest.mark.parametrize("tool", sorted(ROBINHOOD_READ_TOOL_ALLOWLIST))
def test_allowlisted_reads_accepted(tool: str):
    assert classify_tool(tool) is ToolClass.READ
    assert_tool_allowed(tool)  # no raise


def test_unknown_tool_fail_closed():
    assert classify_tool("totally_unknown_tool_xyz") is ToolClass.AMBIGUOUS
    with pytest.raises(PermissionError):
        assert_tool_allowed("totally_unknown_tool_xyz")


def test_mcp_auth_not_allowlisted_for_broker_client():
    """mcp_auth is Cursor-side; production broker client must not invoke it as a trade tool."""
    with pytest.raises(PermissionError):
        assert_tool_allowed("mcp_auth")
