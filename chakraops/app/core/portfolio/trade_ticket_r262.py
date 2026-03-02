# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.2: Trade Ticket v2 — aggregate snapshot/sizing/contract/steps/journal draft. No decision persistence."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Safe action labels (no FAIL/WARN)
ACTION_ENTRY = "Entry"
ACTION_CLOSE = "Close"
ACTION_ROLL = "Roll"
ACTION_HOLD = "Hold"


def _format_as_of_et(ts_utc: Optional[str]) -> str:
    """Format UTC timestamp as ET for display (safe)."""
    if not ts_utc:
        return ""
    try:
        dt = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
        # Simple ET = UTC-5 (no DST)
        et = dt.replace(tzinfo=timezone.utc).astimezone().isoformat()
        return et[:19].replace("T", " ")
    except (ValueError, TypeError):
        return ts_utc[:19] if isinstance(ts_utc, str) else ""


def _recommended_action_label(code: Optional[str]) -> str:
    if not code:
        return ACTION_HOLD
    c = (code or "").strip().upper()
    if c == "ENTRY":
        return ACTION_ENTRY
    if c == "CLOSE":
        return ACTION_CLOSE
    if c == "ROLL":
        return ACTION_ROLL
    if c == "HOLD":
        return ACTION_HOLD
    return c or ACTION_HOLD


def _execution_steps(strategy: str, action: str, is_options: bool) -> List[str]:
    """Generic execution steps (Robinhood-style; copy/paste checklist)."""
    steps: List[str] = []
    strategy = (strategy or "SHARES").strip().upper()
    action = (action or "OPEN").strip().upper()
    if is_options:
        steps.append("1. Open options order ticket (cash-secured put or covered call).")
        steps.append("2. Order type: Limit. Set limit using mark/mid as reference.")
        steps.append("3. Enter quantity (contracts).")
        steps.append("4. Before submit: confirm cash reserve and position caps (Guardrails).")
        steps.append("5. Before submit: check earnings advisory if within 14 days.")
        steps.append("6. After fill: record fill price (premium), fees, and save to Journal.")
    else:
        steps.append("1. Open stock order (buy or sell).")
        steps.append("2. Order type: Limit. Set limit using current quote as reference.")
        steps.append("3. Enter quantity (shares).")
        steps.append("4. Before submit: confirm cash reserve (for buy) and position caps.")
        steps.append("5. After fill: record fill price, fees, and save to Journal.")
    return steps


def build_trade_ticket(
    symbol: str,
    strategy: str,
    action: str,
) -> Dict[str, Any]:
    """
    Build trade ticket payload from latest snapshot/diagnostics/guardrails.
    Deterministic for same inputs; does not persist to decision artifacts.
    Returns dict: snapshot_header, sizing, contract_details, execution_steps, journal_draft, guardrails, earnings_advisory.
    """
    symbol = (symbol or "").strip().upper()
    strategy = (strategy or "SHARES").strip().upper()
    action = (action or "BUY").strip().upper()
    if not symbol:
        return {
            "symbol": "",
            "strategy": strategy,
            "action": action,
            "snapshot_header": {},
            "sizing": {},
            "contract_details": {},
            "execution_steps": _execution_steps(strategy, action, strategy in ("CSP", "CC")),
            "journal_draft": {},
            "guardrails": {},
            "earnings_advisory": {},
            "error": "symbol required",
        }

    out: Dict[str, Any] = {
        "symbol": symbol,
        "strategy": strategy,
        "action": action,
        "snapshot_header": {},
        "sizing": {},
        "contract_details": {},
        "execution_steps": _execution_steps(strategy, action, strategy in ("CSP", "CC")),
        "journal_draft": {},
        "guardrails": {},
        "earnings_advisory": {},
    }

    try:
        from app.core.settings import get_decision_cadence_mode
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2, get_eval_snapshot
        from app.core.portfolio.guardrails_r259 import build_guardrails_snapshot, compute_portfolio_metrics
        from app.core.portfolio.sizing_r260 import apply_sizing
        from app.core.accounts.holdings_db import get_holdings_for_evaluation

        cadence_mode = get_decision_cadence_mode()
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        artifact = store.get_latest()
        eval_snapshot = get_eval_snapshot()
        as_of_utc = None
        if eval_snapshot and isinstance(eval_snapshot, dict):
            as_of_utc = eval_snapshot.get("quote_as_of") or eval_snapshot.get("pipeline_timestamp")
        if not as_of_utc and artifact and getattr(artifact, "metadata", None):
            as_of_utc = (artifact.metadata or {}).get("pipeline_timestamp")
        out["snapshot_header"] = {
            "symbol": symbol,
            "strategy": strategy,
            "action": action,
            "cadence_mode": cadence_mode,
            "as_of_et": _format_as_of_et(as_of_utc),
            "as_of_utc": as_of_utc,
        }

        # Guardrails
        guardrails_snapshot = build_guardrails_snapshot()
        symbol_prices = {}
        if eval_snapshot and isinstance(eval_snapshot, dict):
            for _sym, _v in (eval_snapshot.get("symbols") or {}).items():
                if isinstance(_v, dict) and _v.get("price") is not None:
                    symbol_prices[_sym] = float(_v["price"])
        guardrails_metrics = compute_portfolio_metrics(guardrails_snapshot, symbol_prices=symbol_prices)
        guardrails_snapshot["total_equity"] = guardrails_metrics.get("total_equity")
        guardrails_snapshot["symbol_notionals"] = guardrails_metrics.get("symbol_notionals") or {}
        try:
            from app.core.portfolio.guardrails_r259 import get_guardrails_metrics_and_status
            gms = get_guardrails_metrics_and_status(snapshot=guardrails_snapshot, symbol_prices=symbol_prices)
            if gms and gms.get("metrics"):
                m = gms["metrics"]
                out["guardrails"] = {
                    "available_budget_usd": m.get("available_budget_usd"),
                    "cash_secured_committed_usd": m.get("cash_secured_committed_usd"),
                    "csp_cash_available_usd": m.get("csp_cash_available_usd"),
                }
            else:
                out["guardrails"] = {}
        except Exception:
            out["guardrails"] = {}

        # Diagnostics + sizing for symbol
        row = store.get_symbol(symbol) if store else None
        next_action_code = "HOLD"
        if row:
            summary, candidates, gates, earnings, diagnostics_details = row
            sel_c = None
            if artifact and getattr(artifact, "selected_candidates", None):
                for c in artifact.selected_candidates:
                    if (getattr(c, "symbol", "") or "").strip().upper() == symbol:
                        sel_c = c
                        break
            underlying_price = getattr(summary, "price", None) or getattr(summary, "underlying_price", None) if summary else None
            if underlying_price is None and isinstance(getattr(summary, "price", None), (int, float)):
                underlying_price = float(summary.price)
            shares_for_sym = (get_holdings_for_evaluation() or {}).get(symbol) or 0
            opt_strategy = (getattr(sel_c, "strategy", None) or "CSP").strip().upper() if sel_c else strategy
            strike_val = getattr(sel_c, "strike", None) if sel_c else None
            if strike_val is None and candidates:
                for c in (candidates or [])[:5]:
                    if getattr(c, "strike", None) is not None:
                        strike_val = getattr(c, "strike")
                        break
            candidate = {
                "symbol": symbol,
                "strategy": opt_strategy if strategy in ("CSP", "CC") else "SHARES",
                "strike": strike_val,
                "underlying_price": underlying_price,
                "price": underlying_price,
                "current_shares_qty": shares_for_sym,
                "shares": shares_for_sym,
            }
            if strategy == "SHARES":
                candidate["strategy"] = "SHARES"
                candidate["price"] = underlying_price
            diag_dict = {}
            if diagnostics_details is not None:
                diag_dict = getattr(diagnostics_details, "to_dict", None) and diagnostics_details.to_dict() or (diagnostics_details if isinstance(diagnostics_details, dict) else {})
            symbol_context = {}
            earnings_dict = {}
            if earnings is not None:
                earnings_dict = earnings.to_dict() if hasattr(earnings, "to_dict") else (earnings if isinstance(earnings, dict) else {})
            if isinstance(earnings_dict, dict):
                symbol_context["earnings_days"] = earnings_dict.get("days")
                symbol_context["implied_earnings_move_pct"] = earnings_dict.get("implied_move_pct") or earnings_dict.get("implied_earnings_move_pct")
            tech = (diag_dict.get("technicals") or {}) if isinstance(diag_dict, dict) else {}
            if isinstance(tech, dict):
                symbol_context["atr_pct"] = tech.get("atr_pct")
            sizing_result = apply_sizing(
                candidate,
                guardrails_snapshot,
                guardrails_metrics,
                symbol_context=symbol_context,
            )
            out["sizing"] = {
                "recommended_qty": sizing_result.get("recommended_qty"),
                "recommended_contracts": sizing_result.get("recommended_contracts"),
                "recommended_notional_usd": sizing_result.get("recommended_notional_usd"),
                "sizing_constraints_hit": sizing_result.get("sizing_constraints_hit") or [],
                "sizing_recommended_by": sizing_result.get("sizing_recommended_by"),
                "cash_secured_available_usd": sizing_result.get("cash_secured_available_usd"),
                "csp_risk_proxy_move_pct": sizing_result.get("csp_risk_proxy_move_pct"),
                "csp_risk_proxy_loss_per_contract_usd": sizing_result.get("csp_risk_proxy_loss_per_contract_usd"),
                "csp_risk_proxy_cap_contracts": sizing_result.get("csp_risk_proxy_cap_contracts"),
                "csp_risk_proxy_enforced": sizing_result.get("csp_risk_proxy_enforced"),
            }
            if diag_dict and isinstance(diag_dict, dict):
                next_action_code = (diag_dict.get("next_action_code") or "HOLD").strip().upper()
                out["snapshot_header"]["recommended_action"] = _recommended_action_label(diag_dict.get("next_action_code"))
                opts = diag_dict.get("options_lifecycle") or {}
                if isinstance(opts, dict):
                    out["contract_details"] = {
                        "expiry": (diag_dict.get("candidates") or [{}])[0].get("expiry") if diag_dict.get("candidates") else None,
                        "strike": strike_val or (diag_dict.get("candidates") or [{}])[0].get("strike") if diag_dict.get("candidates") else None,
                        "right": "PUT" if opt_strategy == "CSP" else "CALL",
                        "dte": opts.get("dte") or diag_dict.get("dte"),
                        "mark_value": opts.get("mark_value"),
                        "mark_source": opts.get("mark_source"),
                        "mark_age_sec": opts.get("mark_age_sec"),
                        "premium": getattr(sel_c, "credit_estimate", None) if sel_c else None,
                        "pct_max_profit": opts.get("pct_max_profit"),
                    }
                    if diag_dict.get("candidates") and len(diag_dict["candidates"]) > 0:
                        c0 = diag_dict["candidates"][0]
                        out["contract_details"]["expiry"] = out["contract_details"].get("expiry") or c0.get("expiry")
                        out["contract_details"]["strike"] = out["contract_details"].get("strike") or c0.get("strike")
                        out["contract_details"]["contract_key"] = c0.get("contract_key") or c0.get("occ_symbol")
            else:
                out["snapshot_header"]["recommended_action"] = _recommended_action_label(None)
        else:
            out["snapshot_header"]["recommended_action"] = _recommended_action_label(None)

        # Earnings advisory (advisory only)
        try:
            from app.core.orats.earnings import fetch_earnings_advisory
            ea = fetch_earnings_advisory(symbol, token=None)
            out["earnings_advisory"] = {
                "status": (ea.get("earnings_data_status") or "Unavailable").strip(),
                "next_date": ea.get("earnings_next_date"),
                "days": ea.get("earnings_days"),
                "implied_move_pct": ea.get("implied_earnings_move_pct"),
            }
        except Exception:
            out["earnings_advisory"] = {"status": "Unavailable", "next_date": None, "days": None, "implied_move_pct": None}

        # Journal draft
        from datetime import date
        trade_date = date.today().isoformat()
        out["journal_draft"] = {
            "trade_date": trade_date,
            "symbol": symbol,
            "strategy": strategy,
            "action": "BUY" if action in ("OPEN", "BUY") else "SELL" if action in ("CLOSE", "SELL") else action,
            "qty": out["sizing"].get("recommended_qty") or out["sizing"].get("recommended_contracts") or 0,
            "price": None,
            "premium": None,
            "contract_key": (out.get("contract_details") or {}).get("contract_key"),
            "expiry": (out.get("contract_details") or {}).get("expiry"),
            "strike": (out.get("contract_details") or {}).get("strike"),
            "right": (out.get("contract_details") or {}).get("right"),
            "notes": "",
            "tags": "r262",
        }
    except Exception as e:
        logger.exception("Trade ticket build failed: %s", e)
        out["error"] = "Ticket build failed"
    return out
