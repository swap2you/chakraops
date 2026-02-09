# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 1: Position service — manual execution tracking.

IMPORTANT: ChakraOps NEVER places trades. The "Execute" action records the user's
intention and creates a Position with status=OPEN. The user must execute the trade
manually in their brokerage account.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.positions.models import (
    Position,
    VALID_STATUSES,
    VALID_STRATEGIES,
    generate_position_id,
)
from app.core.positions import store
from app.core.accounts import store as account_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_manual_execute(data: Dict[str, Any]) -> List[str]:
    """Validate manual execution payload. Returns list of error messages."""
    errors: List[str] = []

    if not data.get("account_id"):
        errors.append("account_id is required")
    else:
        account = account_store.get_account(data["account_id"])
        if account is None:
            errors.append(f"Account {data['account_id']} not found")
        elif not account.active:
            errors.append(f"Account {data['account_id']} is not active")

    if not data.get("symbol"):
        errors.append("symbol is required")

    strategy = data.get("strategy", "")
    if strategy not in VALID_STRATEGIES:
        errors.append(f"strategy must be one of {sorted(VALID_STRATEGIES)}")

    if strategy in ("CSP", "CC"):
        contracts = data.get("contracts", 0)
        if not isinstance(contracts, int) or contracts <= 0:
            errors.append("contracts must be a positive integer for options strategies")
    elif strategy == "STOCK":
        quantity = data.get("quantity", 0)
        if not isinstance(quantity, int) or quantity <= 0:
            errors.append("quantity must be a positive integer for STOCK strategy")

    return errors


# ---------------------------------------------------------------------------
# Service operations
# ---------------------------------------------------------------------------


def list_positions(status: Optional[str] = None, symbol: Optional[str] = None) -> List[Position]:
    """List all tracked positions, optionally filtered by symbol."""
    return store.list_positions(status=status, symbol=symbol)


def get_position(position_id: str) -> Optional[Position]:
    """Get a single position."""
    return store.get_position(position_id)


def manual_execute(data: Dict[str, Any]) -> Tuple[Optional[Position], List[str]]:
    """Create a position from manual execution.

    This does NOT place a trade. It records the user's intention to execute.
    The user must execute the actual trade in their brokerage.

    Returns (position, errors).
    """
    errors = validate_manual_execute(data)
    if errors:
        return None, errors

    now = datetime.now(timezone.utc).isoformat()
    position_id = data.get("position_id") or generate_position_id()

    # Phase 4: Optional entry decision snapshot (band, risk_flags, etc.)
    position = Position(
        position_id=position_id,
        account_id=data["account_id"],
        symbol=data["symbol"].upper().strip(),
        strategy=data["strategy"],
        contracts=int(data.get("contracts", 0)),
        strike=data.get("strike"),
        expiration=data.get("expiration"),
        credit_expected=data.get("credit_expected"),
        quantity=data.get("quantity"),
        status="OPEN",
        opened_at=now,
        closed_at=None,
        notes=data.get("notes", ""),
        band=data.get("band"),
        risk_flags_at_entry=data.get("risk_flags_at_entry"),
        portfolio_utilization_pct=data.get("portfolio_utilization_pct"),
        sector_exposure_pct=data.get("sector_exposure_pct"),
        thesis_strength=data.get("thesis_strength"),
        data_sufficiency=data.get("data_sufficiency"),
        risk_amount_at_entry=data.get("risk_amount_at_entry"),
        data_sufficiency_override=data.get("data_sufficiency_override"),
        data_sufficiency_override_source=data.get("data_sufficiency_override_source"),
    )

    try:
        created = store.create_position(position)
        logger.info(
            "[POSITIONS] Manual execution recorded: %s %s %s (%d contracts)",
            position.symbol,
            position.strategy,
            position.position_id,
            position.contracts,
        )
        return created, []
    except ValueError as e:
        return None, [str(e)]
