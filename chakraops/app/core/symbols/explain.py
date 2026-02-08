# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2B: Symbol explain — gate trace, band, score, strategy decision, capital sizing."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.market.company_data import get_company_metadata
from app.core.ranking.service import (
    _get_band,
    _get_primary_strategy,
    _get_primary_candidate_trade,
    _compute_capital_required,
)

logger = logging.getLogger(__name__)


def _load_symbol_from_latest(symbol: str) -> Optional[Dict[str, Any]]:
    """Load symbol data from latest evaluation run."""
    try:
        from app.core.eval.evaluation_store import load_latest_run
        run = load_latest_run()
    except Exception as e:
        logger.warning("[EXPLAIN] Failed to load latest run: %s", e)
        return None

    if not run or not run.symbols:
        return None

    sym_upper = (symbol or "").strip().upper()
    for s in run.symbols:
        if isinstance(s, dict) and (s.get("symbol") or "").strip().upper() == sym_upper:
            return s
    return None


def _normalize_gate(g: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize gate to { name, status, reason, metric? }."""
    status = g.get("status", "UNKNOWN")
    if status in ("PASS", "FAIL", "WAIVED"):
        pass
    else:
        status = "PASS" if g.get("pass", False) else "FAIL"

    reason = g.get("reason") or g.get("detail") or ""
    return {
        "name": g.get("name", "Unknown"),
        "status": status,
        "reason": reason,
        "metric": g.get("metric"),
    }


def get_symbol_explain(symbol: str) -> Dict[str, Any]:
    """Build explain payload for ticker page: company, gates, strategy, capital.

    Returns:
        {
            symbol, company, evaluation_id, evaluated_at,
            verdict, primary_reason, score, band,
            gates: [{ name, status, reason, metric? }],
            primary_strategy, strategy_why_bullets,
            capital_required, capital_pct, account_equity,
            score_breakdown, rank_reasons,
            data_coverage: { present: [], missing: [] },
        }
    """
    sym_upper = (symbol or "").strip().upper()
    if not sym_upper:
        return {"symbol": "", "error": "Symbol required"}

    out: Dict[str, Any] = {
        "symbol": sym_upper,
        "company": get_company_metadata(sym_upper),
        "evaluation_id": None,
        "evaluated_at": None,
        "verdict": "UNKNOWN",
        "primary_reason": "Not in latest evaluation run",
        "score": 0,
        "band": "C",
        "gates": [],
        "primary_strategy": None,
        "strategy_why_bullets": [],
        "capital_required": None,
        "capital_pct": None,
        "account_equity": None,
        "score_breakdown": None,
        "rank_reasons": None,
        "data_coverage": {"present": [], "missing": []},
    }

    sym_data = _load_symbol_from_latest(sym_upper)
    if not sym_data:
        return out

    # Run context
    try:
        from app.core.eval.evaluation_store import load_latest_run
        run = load_latest_run()
        if run:
            out["evaluation_id"] = run.run_id
            out["evaluated_at"] = run.completed_at
    except Exception:
        pass

    # Verdict, score, band
    out["verdict"] = sym_data.get("verdict", "UNKNOWN")
    out["primary_reason"] = sym_data.get("primary_reason", "")
    out["score"] = sym_data.get("score", 0)
    bd = sym_data.get("score_breakdown")
    if bd and isinstance(bd, dict):
        out["score"] = bd.get("composite_score", out["score"])
    out["band"] = _get_band(sym_data)
    out["score_breakdown"] = sym_data.get("score_breakdown")
    out["rank_reasons"] = sym_data.get("rank_reasons")

    # Gates
    gates_raw = sym_data.get("gates", [])
    out["gates"] = [_normalize_gate(g) for g in gates_raw if isinstance(g, dict)]

    # Primary strategy (exclusivity)
    strategy = _get_primary_strategy(sym_data)
    out["primary_strategy"] = strategy

    # Strategy why bullets
    bullets: List[str] = []
    candidates = sym_data.get("candidate_trades", [])
    has_csp = any(t.get("strategy") == "CSP" for t in candidates)
    has_cc = any(t.get("strategy") == "CC" for t in candidates)
    position_open = sym_data.get("position_open", False)

    if strategy == "CSP":
        bullets.append("CSP is primary: put-selling opportunity with defined risk.")
        if not has_cc:
            bullets.append("CC not applicable: no shares held.")
        elif has_cc and not position_open:
            bullets.append("CC not applicable: no tracked shares position.")
        bullets.append("STOCK only if neither options strategy is valid.")
    elif strategy == "CC":
        bullets.append("CC is primary: shares held, covered call overlay.")
        bullets.append("CSP not applicable: already have long shares.")
    elif strategy == "STOCK":
        bullets.append("STOCK is primary: neither CSP nor CC is valid.")
    else:
        bullets.append("No actionable strategy: symbol held or blocked.")

    out["strategy_why_bullets"] = bullets

    # Capital
    trade = _get_primary_candidate_trade(sym_data, strategy) if strategy else None
    capital_required = _compute_capital_required(sym_data, strategy, trade) if strategy else None
    out["capital_required"] = capital_required

    account_equity = None
    try:
        from app.core.accounts.service import get_default_account
        acct = get_default_account()
        if acct and acct.total_capital > 0:
            account_equity = acct.total_capital
    except ImportError:
        pass
    out["account_equity"] = account_equity

    if capital_required and account_equity and account_equity > 0:
        out["capital_pct"] = round(capital_required / account_equity, 4)

    # Data coverage
    present = []
    missing = []
    if sym_data.get("price") is not None:
        present.append("price")
    else:
        missing.append("price")
    if sym_data.get("bid") is not None or sym_data.get("ask") is not None:
        present.append("bid_ask")
    else:
        missing.append("bid_ask")
    if sym_data.get("volume") is not None:
        present.append("volume")
    else:
        missing.append("volume")
    sc = sym_data.get("selected_contract")
    if sc and isinstance(sc, dict):
        c = sc.get("contract", {})
        if c.get("delta") is not None:
            present.append("delta")
        else:
            missing.append("delta")
        if c.get("iv") is not None:
            present.append("iv")
        else:
            missing.append("iv")
    else:
        missing.extend(["delta", "iv"])
    out["data_coverage"] = {"present": present, "missing": missing}

    return out
