# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 1: Account service — validation, business rules, capital-aware sizing.

Rules:
  - Only one default account at a time
  - Percentages must be 1-100
  - total_capital > 0
  - allowed_strategies must be subset of {CSP, CC, STOCK}
  - provider must be in {Robinhood, Schwab, Fidelity, Manual}
  - account_type must be in {Taxable, Roth, IRA, 401k}
"""

from __future__ import annotations

import math
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.accounts.models import (
    Account,
    VALID_ACCOUNT_TYPES,
    VALID_PROVIDERS,
    VALID_STRATEGIES,
    generate_account_id,
)
from app.core.accounts import store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_account_data(data: Dict[str, Any], is_create: bool = True) -> List[str]:
    """Validate account creation/update payload. Returns list of error messages (empty = valid)."""
    errors: List[str] = []

    if is_create:
        if not data.get("provider"):
            errors.append("provider is required")
        if not data.get("account_type"):
            errors.append("account_type is required")

    if "provider" in data and data["provider"] not in VALID_PROVIDERS:
        errors.append(f"provider must be one of {sorted(VALID_PROVIDERS)}")

    if "account_type" in data and data["account_type"] not in VALID_ACCOUNT_TYPES:
        errors.append(f"account_type must be one of {sorted(VALID_ACCOUNT_TYPES)}")

    if "total_capital" in data:
        try:
            tc = float(data["total_capital"])
            if tc <= 0:
                errors.append("total_capital must be > 0")
        except (TypeError, ValueError):
            errors.append("total_capital must be a number")
    elif is_create:
        errors.append("total_capital is required and must be > 0")

    for pct_field in ("max_capital_per_trade_pct", "max_total_exposure_pct"):
        if pct_field in data:
            try:
                v = float(data[pct_field])
                if v < 1 or v > 100:
                    errors.append(f"{pct_field} must be between 1 and 100")
            except (TypeError, ValueError):
                errors.append(f"{pct_field} must be a number")
        elif is_create:
            errors.append(f"{pct_field} is required (1-100)")

    if "allowed_strategies" in data:
        strategies = data["allowed_strategies"]
        if not isinstance(strategies, list) or len(strategies) == 0:
            errors.append("allowed_strategies must be a non-empty list")
        else:
            invalid = set(strategies) - VALID_STRATEGIES
            if invalid:
                errors.append(f"Invalid strategies: {invalid}. Must be subset of {sorted(VALID_STRATEGIES)}")

    return errors


# ---------------------------------------------------------------------------
# Service operations
# ---------------------------------------------------------------------------


def list_accounts() -> List[Account]:
    """List all accounts."""
    return store.list_accounts()


def get_account(account_id: str) -> Optional[Account]:
    """Get a single account."""
    return store.get_account(account_id)


def get_default_account() -> Optional[Account]:
    """Get the current default account."""
    return store.get_default_account()


def create_account(data: Dict[str, Any]) -> Tuple[Optional[Account], List[str]]:
    """Create a new account with validation. Returns (account, errors)."""
    errors = validate_account_data(data, is_create=True)
    if errors:
        return None, errors

    account_id = data.get("account_id") or generate_account_id()
    now = datetime.now(timezone.utc).isoformat()

    account = Account(
        account_id=account_id,
        provider=data["provider"],
        account_type=data["account_type"],
        total_capital=float(data["total_capital"]),
        max_capital_per_trade_pct=float(data["max_capital_per_trade_pct"]),
        max_total_exposure_pct=float(data["max_total_exposure_pct"]),
        allowed_strategies=list(data.get("allowed_strategies", ["CSP"])),
        is_default=bool(data.get("is_default", False)),
        created_at=now,
        updated_at=now,
        active=bool(data.get("active", True)),
    )

    try:
        created = store.create_account(account)
        return created, []
    except ValueError as e:
        return None, [str(e)]


def update_account(account_id: str, data: Dict[str, Any]) -> Tuple[Optional[Account], List[str]]:
    """Update an existing account with validation. Returns (account, errors)."""
    errors = validate_account_data(data, is_create=False)
    if errors:
        return None, errors

    updated = store.update_account(account_id, data)
    if updated is None:
        return None, [f"Account {account_id} not found"]
    return updated, []


def set_default(account_id: str) -> Tuple[Optional[Account], List[str]]:
    """Set an account as default."""
    result = store.set_default_account(account_id)
    if result is None:
        return None, [f"Account {account_id} not found"]
    return result, []


# ---------------------------------------------------------------------------
# Capital-aware CSP sizing (CRITICAL)
# ---------------------------------------------------------------------------


def compute_csp_sizing(
    account: Account,
    strike: float,
) -> Dict[str, Any]:
    """Compute CSP position sizing based on account capital.

    Formula:
        max_capital = account.total_capital * (account.max_capital_per_trade_pct / 100)
        csp_notional = strike * 100
        recommended_contracts = floor(max_capital / csp_notional)

    If recommended_contracts == 0:
        Do NOT recommend CSP.
        Set verdict to HOLD.
        Reason: "Insufficient capital for CSP at this strike"

    Returns dict with sizing details.
    """
    max_capital = account.total_capital * (account.max_capital_per_trade_pct / 100)
    csp_notional = strike * 100
    recommended_contracts = math.floor(max_capital / csp_notional) if csp_notional > 0 else 0

    result: Dict[str, Any] = {
        "account_id": account.account_id,
        "total_capital": account.total_capital,
        "max_capital_per_trade_pct": account.max_capital_per_trade_pct,
        "max_capital": max_capital,
        "strike": strike,
        "csp_notional": csp_notional,
        "recommended_contracts": recommended_contracts,
        "capital_required": csp_notional * recommended_contracts if recommended_contracts > 0 else csp_notional,
        "eligible": recommended_contracts > 0,
    }

    if recommended_contracts == 0:
        result["verdict_override"] = "HOLD"
        result["reason"] = f"Insufficient capital for CSP at ${strike:.2f} strike (requires ${csp_notional:,.0f}, max capital per trade is ${max_capital:,.0f})"
    else:
        result["reason"] = f"{recommended_contracts} contract(s) at ${strike:.2f} = ${csp_notional * recommended_contracts:,.0f} capital required"

    return result


def get_account_equity_from_default() -> Optional[float]:
    """Get account equity from the default account for use in scoring.
    
    This replaces the old ACCOUNT_EQUITY env var / config approach.
    Falls back to None if no default account exists.
    """
    default = get_default_account()
    if default is not None and default.total_capital > 0:
        return default.total_capital
    return None
