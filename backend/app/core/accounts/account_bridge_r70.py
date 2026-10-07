# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 Final Closure — Batch A account bridge.

Bridge configured broker aliases into the application account registry without
storing or exposing full account numbers. Deterministic default when none set.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.accounts.models import Account
from app.core.accounts import store
from app.core.broker.models import ACCOUNT_ALIASES
from app.core.portfolio.capital_authority_r70 import (
    ALIAS_ACCOUNT_TYPE,
    NON_EXECUTION_ALIASES,
    get_capital_snapshot,
)

logger = logging.getLogger(__name__)

# Preferred default when operator has not set one.
DEFAULT_ALIAS_PREFERENCE = ("acct_individual", "acct_ira_roth", "acct_agentic")


def _capital_for_alias(alias: str) -> float:
    cap = get_capital_snapshot(alias, allow_manual_fallback=(alias == "acct_individual"))
    for key in ("equity", "account_value", "cash"):
        v = cap.get(key)
        if v is not None:
            try:
                f = float(v)
                if f > 0:
                    return f
            except (TypeError, ValueError):
                pass
    # Registry requires total_capital > 0; placeholder until fresh sync.
    return 1.0


def ensure_broker_accounts_bridged() -> Dict[str, Any]:
    """Idempotently ensure each ACCOUNT_ALIASES entry exists in accounts.json."""
    created: List[str] = []
    updated: List[str] = []
    existing = {a.account_id: a for a in store.list_accounts()}
    now = datetime.now(timezone.utc).isoformat()

    for alias in ACCOUNT_ALIASES:
        account_type = ALIAS_ACCOUNT_TYPE.get(alias, "Taxable")
        capital = _capital_for_alias(alias)
        if alias in existing:
            # Refresh total_capital from broker when fresh capital > placeholder.
            prev = existing[alias]
            if capital > 1.0 and abs(float(prev.total_capital or 0) - capital) > 0.01:
                store.update_account(
                    alias,
                    {"total_capital": capital, "updated_at": now},
                )
                updated.append(alias)
            continue

        is_default = False  # set below after create if none
        account = Account(
            account_id=alias,
            provider="Robinhood",
            account_type=account_type,
            total_capital=capital,
            max_capital_per_trade_pct=10.0,
            max_total_exposure_pct=50.0,
            allowed_strategies=["CSP", "CC", "STOCK"] if alias not in NON_EXECUTION_ALIASES else ["STOCK"],
            is_default=is_default,
            created_at=now,
            updated_at=now,
            active=True,
        )
        try:
            store.create_account(account)
            created.append(alias)
        except ValueError:
            # Race: already exists
            pass

    default = store.get_default_account()
    established_default: Optional[str] = None
    if default is None:
        accounts = {a.account_id: a for a in store.list_accounts()}
        for pref in DEFAULT_ALIAS_PREFERENCE:
            if pref in accounts and accounts[pref].active:
                store.set_default_account(pref)
                established_default = pref
                break
        if established_default is None:
            actives = [a for a in store.list_accounts() if a.active]
            if actives:
                store.set_default_account(actives[0].account_id)
                established_default = actives[0].account_id

    return {
        "created": created,
        "updated": updated,
        "established_default": established_default,
        "default_account_id": (store.get_default_account().account_id if store.get_default_account() else None),
        "aliases": list(ACCOUNT_ALIASES),
    }


def list_accounts_enriched() -> List[Dict[str, Any]]:
    """List registry accounts, bridging broker aliases first, with capital provenance."""
    ensure_broker_accounts_bridged()
    out: List[Dict[str, Any]] = []
    for a in store.list_accounts():
        d = a.to_dict()
        alias = a.account_id
        if alias in ACCOUNT_ALIASES:
            cap = get_capital_snapshot(alias, allow_manual_fallback=(alias == "acct_individual"))
            d["broker_alias"] = alias
            d["source"] = cap.get("source") or "BROKER_ALIAS"
            d["as_of"] = cap.get("as_of")
            d["capital_state"] = cap.get("state")
            d["stale"] = cap.get("stale")
            d["execution_eligible"] = alias not in NON_EXECUTION_ALIASES and bool(
                cap.get("execution_eligible", True)
            )
            d["taxable_csp_eligible"] = bool(cap.get("taxable_csp_eligible"))
            d["cash"] = cap.get("cash")
            d["buying_power"] = cap.get("buying_power")
            d["equity"] = cap.get("equity")
            # Keep registry total_capital in sync when broker fresh
            if cap.get("state") == "FRESH" and cap.get("equity") is not None:
                d["total_capital"] = float(cap["equity"])
        else:
            d["broker_alias"] = None
            d["source"] = "MANUAL_REGISTRY"
            d["execution_eligible"] = True
            d["taxable_csp_eligible"] = a.account_type == "Taxable"
        out.append(d)
    return out


def get_default_account_ensured() -> Optional[Account]:
    """Return default account after bridging; never silently empty when aliases exist."""
    ensure_broker_accounts_bridged()
    return store.get_default_account()


def get_default_account_enriched() -> Optional[Dict[str, Any]]:
    acct = get_default_account_ensured()
    if acct is None:
        return None
    for row in list_accounts_enriched():
        if row.get("account_id") == acct.account_id:
            return row
    return acct.to_dict()
