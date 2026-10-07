# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 1: Account persistence — JSON file store under out/accounts/accounts.json."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional

from app.core.accounts.models import Account

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _get_accounts_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "accounts"


def _ensure_accounts_dir() -> Path:
    p = _get_accounts_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _accounts_path() -> Path:
    return _ensure_accounts_dir() / "accounts.json"


_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_all() -> List[Account]:
    """Load all accounts from JSON file."""
    path = _accounts_path()
    if not path.exists():
        return []
    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [Account.from_dict(d) for d in data]
            # Backwards compat: dict with "accounts" key
            if isinstance(data, dict) and "accounts" in data:
                return [Account.from_dict(d) for d in data["accounts"]]
            return []
        except Exception as e:
            logger.warning("[ACCOUNTS] Failed to load accounts: %s", e)
            return []


def _save_all(accounts: List[Account]) -> None:
    """Save all accounts to JSON file (atomic write)."""
    path = _accounts_path()
    _ensure_accounts_dir()
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([a.to_dict() for a in accounts], f, indent=2, default=str)
    logger.info("[ACCOUNTS] Saved %d accounts", len(accounts))


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def list_accounts() -> List[Account]:
    """List all accounts."""
    return _load_all()


def get_account(account_id: str) -> Optional[Account]:
    """Get a single account by ID."""
    accounts = _load_all()
    for a in accounts:
        if a.account_id == account_id:
            return a
    return None


def get_default_account() -> Optional[Account]:
    """Get the default account (is_default=True). Returns None if none set."""
    accounts = _load_all()
    for a in accounts:
        if a.is_default and a.active:
            return a
    return None


def create_account(account: Account) -> Account:
    """Create a new account. If is_default, clear other defaults first."""
    accounts = _load_all()
    # Check uniqueness
    for a in accounts:
        if a.account_id == account.account_id:
            raise ValueError(f"Account {account.account_id} already exists")
    # Enforce single default
    if account.is_default:
        for a in accounts:
            a.is_default = False
    accounts.append(account)
    _save_all(accounts)
    logger.info("[ACCOUNTS] Created account %s", account.account_id)
    return account


def update_account(account_id: str, updates: Dict) -> Optional[Account]:
    """Update an existing account. Returns updated account or None if not found."""
    accounts = _load_all()
    target = None
    for a in accounts:
        if a.account_id == account_id:
            target = a
            break
    if target is None:
        return None

    from datetime import datetime, timezone
    # Apply updates
    sizing_keys = ("max_collateral_per_trade", "max_total_collateral", "max_positions_open", "min_credit_per_contract",
                   "max_symbol_collateral", "max_deployed_pct", "max_near_expiry_positions")
    for key in ("provider", "account_type", "total_capital",
                "max_capital_per_trade_pct", "max_total_exposure_pct",
                "allowed_strategies", "active") + sizing_keys:
        if key in updates:
            v = updates[key]
            if key in ("max_positions_open", "max_near_expiry_positions"):
                setattr(target, key, int(v) if v is not None else None)
            elif key in ("max_collateral_per_trade", "max_total_collateral", "min_credit_per_contract", "max_symbol_collateral", "max_deployed_pct"):
                setattr(target, key, float(v) if v is not None else None)
            else:
                setattr(target, key, v)
    target.updated_at = datetime.now(timezone.utc).isoformat()

    # Handle is_default changes
    if "is_default" in updates and updates["is_default"]:
        for a in accounts:
            a.is_default = (a.account_id == account_id)

    _save_all(accounts)
    logger.info("[ACCOUNTS] Updated account %s", account_id)
    return target


def set_default_account(account_id: str) -> Optional[Account]:
    """Set the given account as default; clear all others."""
    accounts = _load_all()
    target = None
    for a in accounts:
        if a.account_id == account_id:
            target = a
    if target is None:
        return None
    for a in accounts:
        a.is_default = (a.account_id == account_id)
    from datetime import datetime, timezone
    target.updated_at = datetime.now(timezone.utc).isoformat()
    _save_all(accounts)
    logger.info("[ACCOUNTS] Set default account to %s", account_id)
    return target
