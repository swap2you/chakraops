# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Broker integration (R37 policy + R52 Robinhood MCP read-only).

R52 enables official Robinhood MCP *read* sync when OAuth token is configured.
Trade execution stays disabled. Write tools are denied. No unofficial clients.
"""

from app.core.broker.allowlist import (
    ROBINHOOD_READ_TOOL_ALLOWLIST,
    ROBINHOOD_WRITE_TOOL_DENYLIST,
    assert_tool_allowed,
    classify_tool,
)
from app.core.broker.read_only_policy import (
    READ_ALLOWLIST,
    WRITE_DENYLIST,
    is_broker_write_forbidden,
)
from app.core.broker.status import robinhood_mcp_read_only_status

# Back-compat alias used by R37 imports / broker routes.
robinhood_integration_status = robinhood_mcp_read_only_status

__all__ = [
    "READ_ALLOWLIST",
    "WRITE_DENYLIST",
    "ROBINHOOD_READ_TOOL_ALLOWLIST",
    "ROBINHOOD_WRITE_TOOL_DENYLIST",
    "is_broker_write_forbidden",
    "assert_tool_allowed",
    "classify_tool",
    "robinhood_integration_status",
    "robinhood_mcp_read_only_status",
]
