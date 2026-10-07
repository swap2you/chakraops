# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2B: Top 3 contract candidates for CSP/CC with sizing."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from app.core.ranking.service import _get_primary_strategy

logger = logging.getLogger(__name__)


def _load_symbol_from_latest(symbol: str) -> Optional[Dict[str, Any]]:
    """Load symbol data from latest evaluation run."""
    try:
        from app.core.eval.evaluation_store import load_latest_run
        run = load_latest_run()
    except Exception:
        return None
    if not run or not run.symbols:
        return None
    sym_upper = (symbol or "").strip().upper()
    for s in run.symbols:
        if isinstance(s, dict) and (s.get("symbol") or "").strip().upper() == sym_upper:
            return s
    return None

# Delta-based labels for CSP puts: more negative = more OTM = conservative
def _csp_label(delta: Optional[float]) -> str:
    if delta is None:
        return "Unknown"
    d = abs(delta)
    if d <= 0.20:
        return "Aggressive"
    if d <= 0.25:
        return "Balanced"
    return "Conservative"


# Delta-based labels for CC calls
def _cc_label(delta: Optional[float]) -> str:
    if delta is None:
        return "Unknown"
    if delta <= 0.20:
        return "Conservative"
    if delta <= 0.28:
        return "Balanced"
    return "Aggressive"


def _contract_to_candidate(
    c: Any,
    strategy: str,
    index: int,
    underlying_price: Optional[float],
) -> Dict[str, Any]:
    """Convert OptionContract to API candidate dict. Use value_or(None) for FieldValues."""
    def _v(fv) -> Optional[float]:
        if fv is None:
            return None
        if hasattr(fv, "value_or"):
            return fv.value_or(None)
        if hasattr(fv, "value"):
            return fv.value
        return None

    bid = _v(getattr(c, "bid", None))
    ask = _v(getattr(c, "ask", None))
    mid = _v(getattr(c, "mid", None))
    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
    delta_val = _v(getattr(c, "delta", None))
    iv_val = _v(getattr(c, "iv", None))

    strike = getattr(c, "strike", None) or 0
    exp = getattr(c, "expiration", None)
    exp_str = exp.isoformat() if hasattr(exp, "isoformat") else str(exp) if exp else None

    premium = mid if mid is not None else (bid if bid is not None else ask)
    collateral = strike * 100 if strategy == "CSP" and strike else None

    label = _csp_label(delta_val) if strategy == "CSP" else _cc_label(delta_val)

    return {
        "rank": index + 1,
        "label": label,
        "expiration": exp_str,
        "strike": strike,
        "delta": delta_val,
        "iv": iv_val,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "premium_per_contract": round(premium, 2) if premium is not None else None,
        "collateral_per_contract": round(collateral, 2) if collateral is not None else None,
        "dte": getattr(c, "dte", None),
        "liquidity_grade": (lambda g: g.value if hasattr(g, "value") else str(g))(
            getattr(c, "get_liquidity_grade", lambda: None)()
        ) if hasattr(c, "get_liquidity_grade") else None,
    }


def _eval_contract_to_candidate(
    trade: Dict[str, Any],
    selected_contract: Optional[Dict[str, Any]],
    strategy: str,
    index: int,
) -> Dict[str, Any]:
    """Build candidate from evaluation trade/selected_contract."""
    sc = selected_contract
    contract = (sc or {}).get("contract", {}) if sc else {}
    strike = trade.get("strike") or contract.get("strike")
    exp = trade.get("expiry") or contract.get("expiration")
    delta = trade.get("delta") or contract.get("delta")
    bid = contract.get("bid")
    ask = contract.get("ask")
    mid = contract.get("mid")
    credit = trade.get("credit_estimate")
    premium = mid if mid is not None else bid if bid is not None else ask if ask is not None else credit
    collateral = strike * 100 if strategy == "CSP" and strike else None

    label = _csp_label(delta) if strategy == "CSP" else _cc_label(delta)

    return {
        "rank": index + 1,
        "label": label,
        "expiration": exp,
        "strike": strike,
        "delta": delta,
        "iv": contract.get("iv"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "premium_per_contract": round(premium, 2) if premium is not None else None,
        "collateral_per_contract": round(collateral, 2) if collateral is not None else None,
        "dte": contract.get("dte"),
        "liquidity_grade": contract.get("liquidity_grade"),
    }


def get_symbol_candidates(symbol: str, strategy: Optional[str] = None) -> Dict[str, Any]:
    """Get top 3 contract candidates for symbol. Strategy defaults to primary from eval.

    Returns:
        {
            symbol, strategy, candidates: [...], recommended_contracts, capital_required,
            capital_pct, account_equity, evaluation_id, evaluated_at,
        }
    """
    sym_upper = (symbol or "").strip().upper()
    if not sym_upper:
        return {"symbol": "", "strategy": None, "candidates": [], "error": "Symbol required"}

    out: Dict[str, Any] = {
        "symbol": sym_upper,
        "strategy": strategy,
        "candidates": [],
        "recommended_contracts": 1,
        "capital_required": None,
        "capital_pct": None,
        "account_equity": None,
        "evaluation_id": None,
        "evaluated_at": None,
    }

    sym_data = _load_symbol_from_latest(sym_upper)
    if not sym_data:
        return out

    try:
        from app.core.eval.evaluation_store import load_latest_run
        run = load_latest_run()
        if run:
            out["evaluation_id"] = run.run_id
            out["evaluated_at"] = run.completed_at
    except Exception:
        pass

    # Determine strategy
    primary = _get_primary_strategy(sym_data)
    if strategy is None:
        strategy = primary
    out["strategy"] = strategy

    if strategy not in ("CSP", "CC"):
        return out

    price = sym_data.get("price")
    selected_contract = sym_data.get("selected_contract")
    candidate_trades = [
        t for t in sym_data.get("candidate_trades", [])
        if t.get("strategy") == strategy
    ]

    # Build from eval first
    eval_candidates: List[Dict[str, Any]] = []
    if selected_contract and isinstance(selected_contract, dict):
        contract = selected_contract.get("contract", {})
        if contract.get("option_type") == ("PUT" if strategy == "CSP" else "CALL"):
            trade = candidate_trades[0] if candidate_trades else {}
            eval_candidates.append(_eval_contract_to_candidate(
                trade, selected_contract, strategy, 0
            ))
    # Also add from candidate_trades when we have fewer than 3
    for i, t in enumerate(candidate_trades):
        if len(eval_candidates) >= 3:
            break
        # Avoid duplicate if already added from selected_contract
        if i == 0 and eval_candidates and selected_contract:
            continue
        eval_candidates.append(_eval_contract_to_candidate(
            t, selected_contract if i == 0 else None, strategy, len(eval_candidates)
        ))

    # Try chain fetch for more candidates
    chain_candidates: List[Dict[str, Any]] = []
    try:
        from app.core.options.orats_chain_provider import get_chain_provider
        from app.core.options.chain_provider import OptionType
        from app.core.config.options_rules import (
            CSP_MIN_DTE, CSP_MAX_DTE, CSP_DELTA_MIN, CSP_DELTA_MAX,
            CC_MIN_DTE, CC_MAX_DTE, CC_DELTA_MIN, CC_DELTA_MAX,
        )

        provider = get_chain_provider()
        expirations = provider.get_expirations(sym_upper)
        today = date.today()
        if strategy == "CSP":
            min_dte, max_dte = CSP_MIN_DTE, CSP_MAX_DTE
            delta_lo, delta_hi = -CSP_DELTA_MAX, -CSP_DELTA_MIN
            target_type = OptionType.PUT
        else:
            min_dte, max_dte = CC_MIN_DTE, CC_MAX_DTE
            delta_lo, delta_hi = CC_DELTA_MIN, CC_DELTA_MAX
            target_type = OptionType.CALL

        in_dte = [e for e in expirations if min_dte <= getattr(e, "dte", (e.expiration - today).days) <= max_dte]
        if not in_dte:
            in_dte = sorted(expirations, key=lambda e: e.expiration)[:3]
        exp_dates = [e.expiration for e in in_dte[:3]]

        chains = provider.get_chains_batch(sym_upper, exp_dates, max_concurrent=2)

        collected: List[Any] = []
        for exp, chain_result in chains.items():
            if not chain_result.success or chain_result.chain is None:
                continue
            chain = chain_result.chain
            contracts = chain.puts if strategy == "CSP" else chain.calls
            for c in contracts:
                d = c.delta.value if hasattr(c.delta, "value") else getattr(c.delta, "value_or", lambda x: None)(None)
                if d is None:
                    continue
                if strategy == "CSP":
                    if not (delta_lo <= d <= delta_hi):
                        continue
                else:
                    if not (delta_lo <= d <= delta_hi):
                        continue
                mid = c.mid.value if hasattr(c.mid, "value") else None
                bid = c.bid.value if hasattr(c.bid, "value") else None
                ask = c.ask.value if hasattr(c.ask, "value") else None
                if mid is None and (bid or ask):
                    mid = (bid or 0 + ask or 0) / 2 if (bid and ask) else (bid or ask)
                if mid is None and bid is None and ask is None:
                    continue
                collected.append((c, mid or 0))

        collected.sort(key=lambda x: -x[1])  # Highest premium first
        for i, (c, _) in enumerate(collected[:3]):
            chain_candidates.append(_contract_to_candidate(c, strategy, i, price))
    except Exception as e:
        logger.warning("[CANDIDATES] Chain fetch failed for %s: %s", sym_upper, e)

    # Prefer chain if we got 3, else merge
    if len(chain_candidates) >= 3:
        out["candidates"] = chain_candidates[:3]
    elif chain_candidates:
        seen = set()
        merged = []
        for ca in chain_candidates + eval_candidates:
            key = (ca.get("strike"), ca.get("expiration"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(ca)
            if len(merged) >= 3:
                break
        for i, ca in enumerate(merged):
            ca["rank"] = i + 1
        out["candidates"] = merged[:3]
    else:
        out["candidates"] = eval_candidates[:3]

    # Sizing from default account
    try:
        from app.core.accounts.service import get_default_account, compute_csp_sizing
        acct = get_default_account()
        if acct and out["candidates"]:
            strike = out["candidates"][0].get("strike")
            if strike and strategy == "CSP":
                sizing = compute_csp_sizing(acct, float(strike))
                out["recommended_contracts"] = sizing.get("recommended_contracts", 1)
                out["capital_required"] = sizing.get("capital_required")
                out["account_equity"] = acct.total_capital
                if acct.total_capital and sizing.get("capital_required"):
                    out["capital_pct"] = round(sizing["capital_required"] / acct.total_capital, 4)
            elif strategy == "CC" and price:
                out["capital_required"] = price * 100  # 100 shares
                out["account_equity"] = acct.total_capital
                if acct.total_capital:
                    out["capital_pct"] = round((price * 100) / acct.total_capital, 4)
    except ImportError:
        pass

    return out
