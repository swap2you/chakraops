# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 Final Closure — Batch A capital authority.

Fresh broker snapshot is LIVE capital authority when available.
Manual recovery is labeled fallback and does not silently drive sizing.
Cash and buying_power remain distinct; CSP uses cash, not margin BP.
Roth / IRA capital is never pooled into taxable CSP collateral.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SOURCE_BROKER = "BROKER_SNAPSHOT"
SOURCE_MANUAL = "MANUAL_RECOVERY"
STATE_FRESH = "FRESH"
STATE_STALE = "STALE"
STATE_UNAVAILABLE = "UNAVAILABLE"
STATE_MANUAL = "MANUAL_NOT_LIVE"

# Account-state freshness for sizing (minutes). Configurable; default 90.
DEFAULT_ACCOUNT_STATE_MAX_AGE_MINUTES = 90.0

# Aliases that must not supply taxable CSP collateral / pooled cash.
NON_TAXABLE_ALIASES = frozenset({"acct_ira_roth"})
# Agentic is never execution-eligible in ChakraOps.
NON_EXECUTION_ALIASES = frozenset({"acct_agentic"})

ALIAS_ACCOUNT_TYPE = {
    "acct_individual": "Taxable",
    "acct_ira_roth": "Roth",
    "acct_agentic": "Taxable",
}


def account_state_max_age_minutes() -> float:
    raw = os.getenv("CHAKRAOPS_BROKER_ACCOUNT_STATE_MAX_AGE_MINUTES")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_ACCOUNT_STATE_MAX_AGE_MINUTES
    try:
        return max(1.0, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_ACCOUNT_STATE_MAX_AGE_MINUTES


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    s = str(ts).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def snapshot_age_minutes(fetched_at: Optional[str], *, now: Optional[datetime] = None) -> Optional[float]:
    dt = _parse_iso(fetched_at)
    if dt is None:
        return None
    now_utc = now or datetime.now(timezone.utc)
    return max(0.0, (now_utc - dt).total_seconds() / 60.0)


def evaluate_snapshot_freshness(
    *,
    snap: Any,
    broker_ready: bool,
    max_age_minutes: Optional[float] = None,
    now: Optional[datetime] = None,
) -> Tuple[str, bool, Optional[float]]:
    """Return (state, age_ok_for_sizing, age_minutes)."""
    if snap is None or not broker_ready:
        return STATE_UNAVAILABLE, False, None
    age = snapshot_age_minutes(getattr(snap, "fetched_at", None), now=now)
    threshold = account_state_max_age_minutes() if max_age_minutes is None else float(max_age_minutes)
    flagged_stale = bool(getattr(snap, "stale", False))
    freshness = str(getattr(snap, "freshness", "") or "").lower()
    age_exceeded = age is not None and age > threshold
    if flagged_stale or freshness == "stale" or age_exceeded:
        return STATE_STALE, False, age
    if age is None and not getattr(snap, "fetched_at", None):
        return STATE_STALE, False, age
    return STATE_FRESH, True, age


def _manual_cash_equity() -> Tuple[float, Optional[float], float, Optional[float]]:
    """cash, total_capital, buying_power, equity from manual recovery holdings_db."""
    try:
        from app.core.accounts.holdings_db import get_account_summary

        summary = get_account_summary() or {}
        cash = float(summary.get("cash") or 0.0)
        total_capital = summary.get("total_capital")
        tc = float(total_capital) if total_capital is not None else None
        bp = summary.get("buying_power")
        buying_power = float(bp) if bp is not None else cash
        equity = tc if tc is not None else cash
        return cash, tc, buying_power, equity
    except Exception:
        return 0.0, None, 0.0, None


def get_capital_snapshot(
    account_alias: str = "acct_individual",
    *,
    allow_manual_fallback: bool = True,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Canonical capital snapshot for one account alias.

    When broker is fresh: cash/buying_power/equity from broker (distinct fields).
    When not: optional MANUAL_RECOVERY labeled fallback; sizing blocked unless policy allows.
    """
    alias = (account_alias or "acct_individual").strip() or "acct_individual"
    from app.core.broker.snapshot_store import load_snapshot
    from app.core.broker.status import robinhood_mcp_read_only_status

    snap = load_snapshot(alias)
    snap_stale_flag = bool(snap.stale) if snap is not None else True
    status = robinhood_mcp_read_only_status(snapshot_stale=snap_stale_flag if snap is not None else None)
    broker_ready = bool(status.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE")) and snap is not None
    state, age_ok, age_min = evaluate_snapshot_freshness(
        snap=snap, broker_ready=broker_ready, now=now
    )

    execution_eligible = alias not in NON_EXECUTION_ALIASES
    taxable_csp_eligible = alias not in NON_TAXABLE_ALIASES and execution_eligible
    account_type = ALIAS_ACCOUNT_TYPE.get(alias, "Taxable")

    base: Dict[str, Any] = {
        "account_alias": alias,
        "account_type": account_type,
        "execution_eligible": execution_eligible,
        "taxable_csp_eligible": taxable_csp_eligible,
        "manual_only": True,
        "trade_execution": False,
        "cash": None,
        "buying_power": None,
        "equity": None,
        "account_value": None,
        "csp_cash_eligible": None,
        "source": None,
        "as_of": None,
        "state": state,
        "stale": state != STATE_FRESH,
        "age_minutes": age_min,
        "account_state_max_age_minutes": account_state_max_age_minutes(),
        "sizing_blocked": True,
        "broker_status": status.get("status"),
        "pooled_from_roth": False,
    }

    if state == STATE_FRESH and snap is not None and age_ok:
        bal = snap.balances
        cash = float(bal.cash) if bal and bal.cash is not None else None
        bp = float(bal.buying_power) if bal and bal.buying_power is not None else None
        equity = float(bal.equity) if bal and bal.equity is not None else None
        # CSP collateral uses cash only — never inflated margin buying power.
        csp_cash = cash if taxable_csp_eligible else 0.0
        sizing_blocked = cash is None or not taxable_csp_eligible
        base.update(
            {
                "cash": cash,
                "buying_power": bp,
                "equity": equity,
                "account_value": equity,
                "csp_cash_eligible": csp_cash,
                "source": SOURCE_BROKER,
                "as_of": snap.fetched_at,
                "state": STATE_FRESH,
                "stale": False,
                "sizing_blocked": sizing_blocked,
                "freshness": getattr(snap, "freshness", None),
                "completeness": getattr(snap, "completeness", None),
            }
        )
        return base

    if state == STATE_STALE and snap is not None:
        bal = snap.balances
        cash = float(bal.cash) if bal and bal.cash is not None else None
        bp = float(bal.buying_power) if bal and bal.buying_power is not None else None
        equity = float(bal.equity) if bal and bal.equity is not None else None
        base.update(
            {
                "cash": cash,
                "buying_power": bp,
                "equity": equity,
                "account_value": equity,
                "csp_cash_eligible": None,  # blocked while stale
                "source": SOURCE_BROKER,
                "as_of": snap.fetched_at,
                "state": STATE_STALE,
                "stale": True,
                "sizing_blocked": True,
                "last_good_preserved": True,
                "freshness": getattr(snap, "freshness", None),
                "completeness": getattr(snap, "completeness", None),
            }
        )
        return base

    if allow_manual_fallback and alias == "acct_individual":
        cash, tc, buying_power, equity = _manual_cash_equity()
        base.update(
            {
                "cash": cash,
                "buying_power": buying_power,
                "equity": equity if equity is not None else tc,
                "account_value": tc if tc is not None else equity,
                "csp_cash_eligible": None,
                "source": SOURCE_MANUAL,
                "as_of": None,
                "state": STATE_MANUAL,
                "stale": True,
                "sizing_blocked": True,  # fail closed for live actionability
                "label": "MANUAL_RECOVERY / NOT LIVE",
            }
        )
        return base

    base.update(
        {
            "source": None,
            "state": STATE_UNAVAILABLE,
            "sizing_blocked": True,
        }
    )
    return base


def get_taxable_csp_capital(*, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Capital for taxable CSP sizing — Individual only; never pools Roth."""
    snap = get_capital_snapshot("acct_individual", allow_manual_fallback=True, now=now)
    return {
        **snap,
        "pooled_from_roth": False,
        "excluded_aliases": sorted(NON_TAXABLE_ALIASES | NON_EXECUTION_ALIASES),
    }


def broker_share_quantities(account_alias: str = "acct_individual") -> Dict[str, int]:
    """Fresh broker share quantities for CC eligibility. Empty when not fresh."""
    cap = get_capital_snapshot(account_alias, allow_manual_fallback=False)
    if cap.get("state") != STATE_FRESH:
        return {}
    from app.core.broker.snapshot_store import load_snapshot

    snap = load_snapshot(account_alias)
    if snap is None:
        return {}
    out: Dict[str, int] = {}
    for p in snap.equity_positions or []:
        sym = (p.symbol or "").strip().upper()
        if not sym:
            continue
        qty = int(float(p.quantity or 0))
        if qty > 0:
            out[sym] = out.get(sym, 0) + qty
    return out


def apply_capital_to_guardrails_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Overwrite cash/share_positions in a guardrails snapshot from capital authority when fresh."""
    cap = get_taxable_csp_capital()
    snapshot = dict(snapshot)
    snapshot["capital_authority"] = {
        "source": cap.get("source"),
        "account_alias": cap.get("account_alias"),
        "as_of": cap.get("as_of"),
        "state": cap.get("state"),
        "stale": cap.get("stale"),
        "sizing_blocked": cap.get("sizing_blocked"),
        "buying_power": cap.get("buying_power"),
        "cash": cap.get("cash"),
        "equity": cap.get("equity"),
    }
    if cap.get("state") == STATE_FRESH and cap.get("cash") is not None:
        snapshot["cash"] = float(cap["cash"])
        if cap.get("equity") is not None:
            snapshot["total_capital"] = float(cap["equity"])
        shares = broker_share_quantities("acct_individual")
        if shares:
            # Prefer broker shares for exposure/CC; keep manual as diagnostic only
            snapshot["share_positions"] = [
                {"symbol": s, "quantity": q, "avg_cost": None, "authority": SOURCE_BROKER}
                for s, q in sorted(shares.items())
            ]
            snapshot["holdings"] = [
                {"symbol": s, "shares": q, "avg_cost": None, "authority": SOURCE_BROKER}
                for s, q in sorted(shares.items())
            ]
    snapshot["sizing_blocked"] = bool(cap.get("sizing_blocked"))
    return snapshot


def list_account_capital_matrix(aliases: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    from app.core.broker.models import ACCOUNT_ALIASES

    use = list(aliases) if aliases else list(ACCOUNT_ALIASES)
    return [get_capital_snapshot(a, allow_manual_fallback=(a == "acct_individual")) for a in use]


def get_broker_freshness_view(
    account_alias: str = "acct_individual",
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Canonical age-based broker freshness for capital, lenses, Slack, and conflict checks.

    state is exactly one of FRESH | STALE | UNAVAILABLE.
    open_position_count is an int only when FRESH; otherwise None (callers must say UNKNOWN).
    """
    alias = (account_alias or "acct_individual").strip() or "acct_individual"
    from app.core.broker.snapshot_store import load_snapshot
    from app.core.broker.status import robinhood_mcp_read_only_status

    snap = load_snapshot(alias)
    # Token / auth readiness without trusting the stored boolean alone.
    status = robinhood_mcp_read_only_status(snapshot_stale=None)
    token_ready = bool(status.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE")) or (
        str(status.get("status") or "").upper() in ("READ_ONLY_AVAILABLE", "STALE")
        and bool((status.get("auth") or {}).get("authenticated") or status.get("oauth", {}).get("authenticated"))
    )
    # Prefer explicit authenticated flag when present.
    auth = status.get("auth") or status.get("oauth") or {}
    if auth.get("authenticated") is True:
        token_ready = True
    if str(status.get("status") or "").upper() in ("UNAUTHENTICATED", "AUTH_REQUIRED", "ERROR"):
        # Still allow age evaluation when a snapshot exists but mark UNAVAILABLE if no snap.
        if snap is None:
            token_ready = False

    broker_ready = bool(token_ready) and snap is not None
    state, _age_ok, age_min = evaluate_snapshot_freshness(
        snap=snap, broker_ready=broker_ready, now=now
    )
    # Pass effective age-based stale into status for observability consistency.
    effective_stale = state != STATE_FRESH
    status_eff = robinhood_mcp_read_only_status(
        snapshot_stale=effective_stale if snap is not None else None
    )

    open_count: Optional[int] = None
    if state == STATE_FRESH and snap is not None:
        eq = len(snap.equity_positions or [])
        op = len(snap.option_positions or [])
        open_count = eq + op

    return {
        "account_alias": alias,
        "state": state,
        "stale": state != STATE_FRESH,
        "sizing_blocked": state != STATE_FRESH,
        "as_of": getattr(snap, "fetched_at", None) if snap is not None else None,
        "age_minutes": age_min,
        "account_state_max_age_minutes": account_state_max_age_minutes(),
        "source": getattr(snap, "source", None) if snap is not None else None,
        "freshness": getattr(snap, "freshness", None) if snap is not None else None,
        "open_position_count": open_count,
        "broker_open_display": str(open_count) if open_count is not None else "UNKNOWN",
        "broker_status": status_eff.get("status"),
        "manual_only": True,
        "trade_execution": False,
    }


def robinhood_conflict_check_label(
    freshness_state: str,
    *,
    conflict: Optional[bool] = None,
    aggregate: bool = False,
    checked_all: Optional[bool] = None,
) -> str:
    """Truthful Robinhood conflict-check wording for Slack/UI previews.

    Aggregate / universe-level signals must never claim CLEAR unless every
    referenced symbol was individually checked against a fresh snapshot.
    """
    st = (freshness_state or "").strip().upper()
    if aggregate:
        if checked_all is False or conflict is None:
            if not st or st == STATE_UNAVAILABLE:
                return "Conflict check: NOT PERFORMED — no symbol supplied"
            if st != STATE_FRESH:
                return "Conflict check: NOT PERFORMED — no symbol supplied"
            return "Conflict check: PARTIAL — see candidate details"
        if conflict is True:
            return "Robinhood conflict check: CONFLICT — existing position detected"
        if conflict is False and checked_all is True and st == STATE_FRESH:
            return "Robinhood conflict check: CLEAR"
        return "Conflict check: PARTIAL — see candidate details"
    if st == STATE_FRESH:
        if conflict is True:
            return "Robinhood conflict check: CONFLICT — existing position detected"
        if conflict is False:
            return "Robinhood conflict check: CLEAR"
        return "Robinhood conflict check: NOT PERFORMED — no symbol supplied"
    if st == STATE_STALE:
        return "Robinhood conflict check: UNKNOWN — snapshot stale"
    return "Robinhood conflict check: NOT PERFORMED — broker unavailable"


def symbol_has_broker_conflict(
    symbol: Optional[str],
    *,
    account_alias: str = "acct_individual",
    freshness: Optional[Dict[str, Any]] = None,
) -> Optional[bool]:
    """Return True/False only when freshness is FRESH and a symbol is supplied; else None."""
    view = freshness or get_broker_freshness_view(account_alias)
    if view.get("state") != STATE_FRESH:
        return None
    sym = (symbol or "").strip().upper()
    if not sym:
        # Aggregate / universe signal: no symbol → unknown (never CLEAR).
        return None
    from app.core.broker.snapshot_store import load_snapshot

    snap = load_snapshot(account_alias)
    if snap is None:
        return None
    for p in snap.equity_positions or []:
        if (getattr(p, "symbol", "") or "").strip().upper() == sym:
            return True
    for p in snap.option_positions or []:
        if (getattr(p, "symbol", "") or "").strip().upper() == sym:
            return True
    return False
