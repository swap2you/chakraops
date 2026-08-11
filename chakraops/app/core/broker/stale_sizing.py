# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R64: block CSP/new sizing helpers when broker collateral is stale or untrusted."""

from __future__ import annotations

from typing import Any, Dict, Optional


CONSTRAINT_BROKER_COLLATERAL_STALE = "BROKER_COLLATERAL_STALE"
CONSTRAINT_BROKER_AUTH_UNTRUSTED = "BROKER_AUTH_UNTRUSTED"


def broker_collateral_trusted(
    *,
    status: Optional[str] = None,
    stale: bool = False,
    read_only_available: bool = False,
) -> bool:
    """True when live/read-only broker collateral may be used for sizing."""
    if stale:
        return False
    st = (status or "").strip().upper()
    if st in {"STALE", "ERROR", "UNAUTHENTICATED", "AUTH_REQUIRED"}:
        return False
    if st == "READ_ONLY_AVAILABLE" and read_only_available:
        return True
    return False


def sizing_block_for_stale_collateral(
    *,
    status: Optional[str] = None,
    stale: bool = False,
    read_only_available: bool = False,
    strategy: str = "CSP",
) -> Dict[str, Any]:
    """Return sizing gate payload. Never enables trade execution.

    When blocked, recommended size is zero and constraints list why.
    """
    strat = (strategy or "").strip().upper() or "CSP"
    trusted = broker_collateral_trusted(
        status=status,
        stale=stale,
        read_only_available=read_only_available,
    )
    constraints = []
    if stale or (status or "").strip().upper() == "STALE":
        constraints.append(CONSTRAINT_BROKER_COLLATERAL_STALE)
    if (status or "").strip().upper() in {"UNAUTHENTICATED", "AUTH_REQUIRED", "ERROR"}:
        constraints.append(CONSTRAINT_BROKER_AUTH_UNTRUSTED)
    if not read_only_available and (status or "").strip().upper() != "READ_ONLY_AVAILABLE":
        if CONSTRAINT_BROKER_AUTH_UNTRUSTED not in constraints:
            constraints.append(CONSTRAINT_BROKER_AUTH_UNTRUSTED)

    blocked = not trusted
    return {
        "blocked": blocked,
        "trusted_collateral": trusted,
        "recommended_contracts": 0 if blocked else None,
        "recommended_qty": 0 if blocked else None,
        "sizing_constraints_hit": constraints if blocked else [],
        "reason": (
            "Broker collateral stale or untrusted — CSP/new sizing blocked"
            if blocked
            else "Broker collateral trusted for advisory sizing"
        ),
        "strategy": strat,
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
    }
