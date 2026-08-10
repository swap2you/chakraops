# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52 Robinhood MCP tool allowlist / write denylist.

Only explicitly allowlisted READ tools may be invoked by the broker client.
No generic catch-all MCP tool proxy exists by design.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet

# Explicit READ allowlist — must match production Robinhood MCP read tools.
ROBINHOOD_READ_TOOL_ALLOWLIST: FrozenSet[str] = frozenset(
    {
        "get_accounts",
        "get_portfolio",
        "get_equity_positions",
        "get_option_positions",
        "get_equity_orders",
        "get_option_orders",
        "get_equity_quotes",
        "get_option_quotes",
        "get_option_chains",
        "get_option_instruments",
        "get_option_historicals",
        "get_equity_fundamentals",
        "get_equity_historicals",
        "get_equity_price_book",
        "get_equity_tax_lots",
        "get_equity_technical_indicators",
        "get_equity_tradability",
        "get_financials",
        "get_index_historicals",
        "get_index_quotes",
        "get_indexes",
        "get_earnings_calendar",
        "get_earnings_results",
        "get_option_level_upgrade_info",
        "get_option_watchlist",
        "get_pnl_trade_history",
        "get_popular_watchlists",
        "get_realized_pnl",
        "get_scanner_filter_specs",
        "get_scans",
        "get_watchlist_items",
        "get_watchlists",
        "search",
        "review_equity_order",
        "review_option_order",
    }
)

# Known WRITE tools — never invoke. Strings only for classification / tests.
ROBINHOOD_WRITE_TOOL_DENYLIST: FrozenSet[str] = frozenset(
    {
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
    }
)

# Substring heuristics for defensive classification of unknown tool names.
DENY_WRITE_SUBSTRINGS: FrozenSet[str] = frozenset(
    {
        "place_",
        "cancel_",
        "exercise_",
        "add_to_",
        "add_option_",
        "remove_from_",
        "remove_option_",
        "create_watchlist",
        "update_watchlist",
        "create_scan",
        "update_scan_",
        "run_scan",
        "follow_watchlist",
        "unfollow_watchlist",
    }
)


class ToolClass(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    AMBIGUOUS = "AMBIGUOUS"


def classify_tool(name: str) -> ToolClass:
    """Classify a tool name as READ, WRITE, or AMBIGUOUS."""
    key = (name or "").strip()
    if not key:
        return ToolClass.AMBIGUOUS
    if key in ROBINHOOD_READ_TOOL_ALLOWLIST:
        return ToolClass.READ
    if key in ROBINHOOD_WRITE_TOOL_DENYLIST:
        return ToolClass.WRITE
    lower = key.lower()
    for sub in DENY_WRITE_SUBSTRINGS:
        if sub in lower:
            return ToolClass.WRITE
    # Unknown non-allowlisted tools are ambiguous — fail closed at assert.
    return ToolClass.AMBIGUOUS


def assert_tool_allowed(name: str) -> None:
    """Raise PermissionError unless ``name`` is an allowlisted READ tool."""
    key = (name or "").strip()
    cls = classify_tool(key)
    if cls is ToolClass.READ and key in ROBINHOOD_READ_TOOL_ALLOWLIST:
        return
    if cls is ToolClass.WRITE or key in ROBINHOOD_WRITE_TOOL_DENYLIST:
        raise PermissionError(
            f"Robinhood MCP tool '{key}' is WRITE/denied — R52 read-only policy forbids invocation"
        )
    raise PermissionError(
        f"Robinhood MCP tool '{key}' is not on ROBINHOOD_READ_TOOL_ALLOWLIST — fail closed"
    )
