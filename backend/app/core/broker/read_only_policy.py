# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Broker write-denylist policy (R37) + R52 status delegation.

R37 established hard write denylist verbs. R52 supersedes permanent Robinhood
NO-GO for the *official* MCP read path — see ``status.robinhood_mcp_read_only_status``.

Unofficial private APIs / robin_stocks / browser-login automation remain forbidden.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

from app.core.broker.status import robinhood_mcp_read_only_status

# Conceptual ChakraOps-level read surface labels (not MCP tool names).
# MCP tool allowlist lives in allowlist.ROBINHOOD_READ_TOOL_ALLOWLIST (R52).
READ_ALLOWLIST: FrozenSet[str] = frozenset()

READ_ALLOWLIST_CONCEPTUAL: FrozenSet[str] = frozenset(
    {
        "balances",
        "positions",
        "orders_history",
        "transactions",
    }
)

# Hard write denylist — any matching operation is forbidden.
WRITE_DENYLIST: FrozenSet[str] = frozenset(
    {
        "place",
        "buy",
        "sell",
        "submit",
        "route",
        "cancel",
        "exercise",
        "assign",
        "rebalance",
        "execute",
        "modify_order",
    }
)


def is_broker_write_forbidden(op: str) -> bool:
    """Return True when ``op`` matches a hard write-deny verb (case-insensitive)."""
    key = (op or "").strip().lower()
    if not key:
        return False
    if key in WRITE_DENYLIST:
        return True
    # Also match compound tokens like "place_order" / "buy_shares".
    for verb in WRITE_DENYLIST:
        if key == verb or key.startswith(verb + "_") or key.endswith("_" + verb) or f"_{verb}_" in key:
            return True
    return False


def robinhood_integration_status() -> Dict[str, Any]:
    """R52: MCP read-only status (READ_ONLY_AVAILABLE or UNAUTHENTICATED)."""
    return robinhood_mcp_read_only_status()
