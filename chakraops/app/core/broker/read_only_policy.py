# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R37 broker read-only policy — hard write denylist; Robinhood NO-GO.

Official Robinhood public docs (https://docs.robinhood.com/) cover Crypto Trading
API only. There is no official public brokerage API for stocks/options Wheel
portfolio sync. Unofficial private APIs, robin_stocks / api.robinhood.com clients,
and browser-login automation are forbidden by the master program (NO-GO).

This module encodes the safety surface only. It does not connect to any broker.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

# Conceptual future read surface for a *supported* broker (balances, positions,
# order history, transactions). Empty/disabled for Robinhood — no official
# equity/options portfolio API and no unofficial client may be added.
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

_RH_NO_GO_REASON = (
    "No official public Robinhood brokerage API for stocks/options portfolio "
    "sync (docs.robinhood.com is Crypto Trading API only). Unofficial private "
    "API / robin-stocks / browser-login automation are forbidden. Continue with "
    "manual portfolio trusted snapshot."
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
    """Stable NO-GO status for Robinhood (no credentials, no sync)."""
    return {
        "status": "NO_GO",
        "reason": _RH_NO_GO_REASON,
        "manual_portfolio": True,
        "manual_only": True,
        "trade_execution": False,
        "broker": "robinhood",
        "read_allowlist_enabled": False,
        "read_allowlist": sorted(READ_ALLOWLIST),
        "write_denylist": sorted(WRITE_DENYLIST),
    }
