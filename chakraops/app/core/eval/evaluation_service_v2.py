# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.6: ONE evaluation engine — produces DecisionArtifactV2, writes to store."""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.eval.decision_artifact_v2 import (
    CandidateRow,
    DecisionArtifactV2,
    EarningsInfo,
    GateEvaluation,
    SymbolDiagnosticsDetails,
    SymbolEvalSummary,
    assign_band,
    assign_band_reason,
    compute_rank_score,
)
from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2

logger = logging.getLogger(__name__)


def evaluate_universe(
    symbols: List[str],
    mode: str = "LIVE",
    output_dir: Optional[str] = None,
) -> DecisionArtifactV2:
    """
    ONE evaluation engine for batch universe.
    Runs staged evaluation, produces DecisionArtifactV2, stores in EvaluationStoreV2.
    Returns the artifact. Also writes decision_latest.json (v2) to disk.
    """
    from app.core.eval.universe_evaluator import run_universe_evaluation_staged
    from app.market.market_hours import get_market_phase

    if output_dir:
        from pathlib import Path as PathLib
        from app.core.eval.evaluation_store_v2 import set_output_dir
        set_output_dir(PathLib(output_dir))

    phase = get_market_phase() or "UNKNOWN"
    ts = datetime.now(timezone.utc).isoformat()

    # Run staged evaluation (ONE engine)
    result = run_universe_evaluation_staged(symbols, use_staged=True)
    staged_symbols = getattr(result, "symbols", []) or []

    # Build result map by symbol
    by_symbol: Dict[str, Any] = {}
    for s in staged_symbols:
        sym = (getattr(s, "symbol", "") or "").strip().upper()
        if sym:
            by_symbol[sym] = s

    # ONE ROW PER UNIVERSE SYMBOL (fill NOT_EVALUATED for missing)
    symbols_out: List[SymbolEvalSummary] = []
    selected_candidates: List[CandidateRow] = []
    candidates_by_symbol: Dict[str, List[CandidateRow]] = {}
    gates_by_symbol: Dict[str, List[GateEvaluation]] = {}
    earnings_by_symbol: Dict[str, EarningsInfo] = {}
    diagnostics_by_symbol: Dict[str, SymbolDiagnosticsDetails] = {}

    stage2_count = 0
    eligible_count = 0

    for sym in symbols:
        sym_upper = sym.strip().upper()
        sr = by_symbol.get(sym_upper)

        if sr is None:
            # Not in results — NOT_EVALUATED (band never null, use D)
            symbols_out.append(SymbolEvalSummary(
                symbol=sym_upper,
                verdict="NOT_EVALUATED",
                final_verdict="NOT_EVALUATED",
                score=None,
                band="D",
                band_reason=assign_band_reason(None),
                primary_reason="Not evaluated",
                stage_status="NOT_RUN",
                stage1_status="NOT_RUN",
                stage2_status="NOT_RUN",
                provider_status=None,
                data_freshness=None,
                evaluated_at=None,
                strategy=None,
                price=None,
                expiration=None,
                has_candidates=False,
                candidate_count=0,
            ))
            earnings_by_symbol[sym_upper] = EarningsInfo(None, None, "Not evaluated")
            _empty: Dict[str, Any] = {}
            diagnostics_by_symbol[sym_upper] = SymbolDiagnosticsDetails(
                technicals=_empty,
                exit_plan={"t1": None, "t2": None, "t3": None, "stop": None},
                risk_flags=_empty,
                explanation=_empty,
                stock=_empty,
                symbol_eligibility=_empty,
                liquidity=_empty,
            )
            continue

        verdict = str(getattr(sr, "verdict", "HOLD") or "HOLD").upper()
        if verdict not in ("ELIGIBLE", "HOLD", "BLOCKED", "NOT_EVALUATED"):
            verdict = "HOLD"
        score = getattr(sr, "score", None)  # final score (after caps)
        band = assign_band(score)  # Phase 10.1: band from final_score only
        stage_reached = getattr(sr, "stage_reached", None)
        stage_reached_val = getattr(stage_reached, "value", str(stage_reached) or "STAGE1_ONLY")
        stage2_ran = stage_reached_val == "STAGE2_CHAIN"
        if stage2_ran:
            stage2_count += 1
        if verdict == "ELIGIBLE":
            eligible_count += 1

        cds = getattr(sr, "candidate_trades", []) or []
        cand_list: List[CandidateRow] = []
        for ct in cds:
            ct_dict = asdict(ct) if hasattr(ct, "__dataclass_fields__") else (ct if isinstance(ct, dict) else {})
            cand_list.append(CandidateRow(
                symbol=sym_upper,
                strategy=str(ct_dict.get("strategy", "CSP")),
                expiry=ct_dict.get("expiry"),
                strike=ct_dict.get("strike"),
                delta=ct_dict.get("delta"),
                credit_estimate=ct_dict.get("credit_estimate"),
                max_loss=ct_dict.get("max_loss"),
                why_this_trade=ct_dict.get("why_this_trade"),
            ))
        candidates_by_symbol[sym_upper] = cand_list

        sc = getattr(sr, "selected_contract", None)  # dict from SymbolEvaluationResult
        strategy_val = None
        expiry_val = getattr(sr, "selected_expiration", None)
        if expiry_val and hasattr(expiry_val, "isoformat"):
            expiry_val = str(expiry_val.isoformat())[:10]
        elif expiry_val:
            expiry_val = str(expiry_val)[:10]

        if verdict == "ELIGIBLE":
            _opt_sym: Optional[str] = None
            _ct_key: Optional[str] = None
            if sc and isinstance(sc, dict):
                strategy_val = str(sc.get("strategy", "CSP"))
                expiry_val = expiry_val or str(sc.get("expiration", "") or sc.get("expiry", ""))[:10]
                contract_d = sc.get("contract") or sc
                _opt_sym = contract_d.get("option_symbol") if isinstance(contract_d, dict) else None
                st = sc.get("strike") or (contract_d.get("strike") if isinstance(contract_d, dict) else None)
                if st is not None and expiry_val:
                    opt_type = "PUT" if (strategy_val or "CSP").upper() == "CSP" else "CALL"
                    _ct_key = f"{st}-{expiry_val[:10]}-{opt_type}"
                selected_candidates.append(CandidateRow(
                    symbol=sym_upper,
                    strategy=strategy_val,
                    expiry=expiry_val or None,
                    strike=sc.get("strike") or (contract_d.get("strike") if isinstance(contract_d, dict) else None),
                    delta=sc.get("delta") or (contract_d.get("delta") if isinstance(contract_d, dict) else None),
                    credit_estimate=sc.get("credit_estimate"),
                    max_loss=sc.get("max_loss"),
                    why_this_trade=sc.get("selection_reason") or sc.get("why_this_trade"),
                    contract_key=_ct_key,
                    option_symbol=_opt_sym,
                ))
            elif cds:
                first = cds[0]
                ft = asdict(first) if hasattr(first, "__dataclass_fields__") else (first if isinstance(first, dict) else {})
                strategy_val = str(ft.get("strategy", "CSP"))
                expiry_val = expiry_val or str(ft.get("expiry") or ft.get("expiration") or "")[:10]
                _opt_sym = ft.get("option_symbol")
                st = ft.get("strike")
                _ct_key = f"{st}-{expiry_val[:10]}-{'PUT' if (strategy_val or 'CSP').upper() == 'CSP' else 'CALL'}" if (st is not None and expiry_val) else None
                selected_candidates.append(CandidateRow(
                    symbol=sym_upper,
                    strategy=strategy_val,
                    expiry=expiry_val or None,
                    strike=st,
                    delta=ft.get("delta"),
                    credit_estimate=ft.get("credit_estimate"),
                    max_loss=ft.get("max_loss"),
                    why_this_trade=ft.get("why_this_trade"),
                    contract_key=_ct_key,
                    option_symbol=_opt_sym,
                ))

        gates: List[GateEvaluation] = []
        for g in getattr(sr, "gates", []) or []:
            if isinstance(g, dict):
                gates.append(GateEvaluation(
                    name=g.get("name", ""),
                    status=g.get("status", "SKIP"),
                    reason=g.get("reason"),
                ))
        gates_by_symbol[sym_upper] = gates

        earnings_by_symbol[sym_upper] = EarningsInfo(
            earnings_days=getattr(sr, "earnings_days", None),
            earnings_block=getattr(sr, "earnings_blocked", None),
            note="Not evaluated" if not getattr(sr, "earnings_days", None) and not getattr(sr, "earnings_blocked", None) else None,
        )

        stage1_status = "PASS" if stage_reached_val in ("STAGE1_ONLY", "STAGE2_CHAIN") else "FAIL"
        stage2_status = "PASS" if (stage2_ran and getattr(sr, "liquidity_ok", False)) else ("FAIL" if stage2_ran else "NOT_RUN")
        provider_ok = (getattr(sr, "data_completeness", 0) or 0) >= 0.75
        provider_status = "OK" if provider_ok else "WARN"

        # Phase 7.7: max_loss, underlying_price, score_breakdown, band_reason
        max_loss_val: Optional[float] = None
        if sc and isinstance(sc, dict):
            max_loss_val = sc.get("max_loss")
        if max_loss_val is None and cds:
            first_ct = asdict(cds[0]) if hasattr(cds[0], "__dataclass_fields__") else (cds[0] if isinstance(cds[0], dict) else {})
            max_loss_val = first_ct.get("max_loss")
        price_val = getattr(sr, "price", None)
        score_bd = getattr(sr, "score_breakdown", None)
        band_rsn = assign_band_reason(score)  # NEVER use sr.band_reason — band_reason from score only, no verdict
        # Phase 8.0: ranking fields
        capital_req: Optional[float] = max_loss_val if max_loss_val is not None else (price_val * 100 if price_val and price_val > 0 else None)
        expected_cr: Optional[float] = None
        prem_yield: Optional[float] = None
        mcap: Optional[float] = getattr(sr, "market_cap", None)
        if sc and isinstance(sc, dict):
            expected_cr = sc.get("credit_estimate")
        if expected_cr is None and cds:
            first_ct = asdict(cds[0]) if hasattr(cds[0], "__dataclass_fields__") else (cds[0] if isinstance(cds[0], dict) else {})
            expected_cr = first_ct.get("credit_estimate")
        if capital_req and capital_req > 0 and expected_cr is not None:
            prem_yield = (expected_cr / capital_req) * 100
        rk = compute_rank_score(band, float(score) if score is not None else None, prem_yield, capital_req, mcap)
        raw_s = getattr(sr, "raw_score", None)
        caps_s = getattr(sr, "score_caps", None)
        if score_bd and hasattr(score_bd, "to_dict"):
            score_bd = score_bd.to_dict()
        if score_bd and isinstance(score_bd, dict):
            score_bd = dict(score_bd)
            if raw_s is not None:
                score_bd["raw_score"] = raw_s
            score_bd["final_score"] = score
            if caps_s:
                score_bd["score_caps"] = caps_s
        symbols_out.append(SymbolEvalSummary(
            symbol=sym_upper,
            verdict=verdict,
            final_verdict=verdict,
            score=score,
            band=band,
            final_score=score,
            pre_cap_score=raw_s,
            primary_reason=getattr(sr, "primary_reason", None) or "",
            stage_status="RUN",
            stage1_status=stage1_status,
            stage2_status=stage2_status,
            provider_status=provider_status,
            data_freshness=getattr(sr, "quote_date", None) or getattr(sr, "fetched_at", None),
            evaluated_at=getattr(sr, "fetched_at", None) or ts,
            strategy=strategy_val,
            price=price_val,
            expiration=expiry_val,
            has_candidates=len(cds) > 0,
            candidate_count=len(cds),
            score_breakdown=score_bd,
            raw_score=raw_s,
            score_caps=caps_s,
            band_reason=band_rsn,
            max_loss=max_loss_val,
            underlying_price=price_val,
            capital_required=capital_req,
            expected_credit=expected_cr,
            premium_yield_pct=prem_yield,
            market_cap=mcap,
            rank_score=rk,
        ))

        # Phase 7.7: diagnostics_by_symbol
        diagnostics_by_symbol[sym_upper] = _build_diagnostics_details(sr, sym_upper, ts)

    run_id_val = str(uuid.uuid4())
    metadata = {
        "artifact_version": "v2",
        "mode": mode,
        "pipeline_timestamp": ts,
        "evaluation_timestamp_utc": ts,
        "run_id": run_id_val,
        "market_phase": phase,
        "universe_size": len(symbols),
        "evaluated_count_stage1": len(staged_symbols),
        "evaluated_count_stage2": stage2_count,
        "eligible_count": eligible_count,
        "warnings": [],
    }

    artifact = DecisionArtifactV2(
        metadata=metadata,
        symbols=symbols_out,
        selected_candidates=selected_candidates,
        candidates_by_symbol=candidates_by_symbol,
        gates_by_symbol=gates_by_symbol,
        earnings_by_symbol=earnings_by_symbol,
        diagnostics_by_symbol=diagnostics_by_symbol,
        warnings=[],
    )

    # Store (writes to disk)
    store = get_evaluation_store_v2()
    store.set_latest(artifact)

    logger.info("[EVAL_SVC_V2] evaluate_universe: %d symbols, %d stage2, %d eligible", len(symbols), stage2_count, eligible_count)
    return artifact


def _build_diagnostics_details(sr: Any, sym_upper: str, ts: str) -> SymbolDiagnosticsDetails:
    """Build SymbolDiagnosticsDetails from staged SymbolEvaluationResult."""
    el = getattr(sr, "eligibility_trace", None) or {}
    st2 = getattr(sr, "stage2_trace", None) or {}
    computed = el.get("computed") or {}
    technicals = {
        "rsi": computed.get("RSI14") or el.get("rsi14"),
        "atr": computed.get("ATR14"),
        "atr_pct": computed.get("ATR_pct") or el.get("atr_pct"),
        "support_level": computed.get("support_level") or el.get("support_level"),
        "resistance_level": computed.get("resistance_level") or el.get("resistance_level"),
    }
    spot = getattr(sr, "price", None)
    mode_decision = (el.get("mode_decision") or "CSP").strip().upper()
    exit_plan_dict: Dict[str, Any] = {"t1": None, "t2": None, "t3": None, "stop": None}
    try:
        from app.core.lifecycle.exit_planner import build_exit_plan
        ep = build_exit_plan(sym_upper, mode_decision, spot, el, st2, None)
        sp = (ep.get("structure_plan") or {}) if isinstance(ep, dict) else {}
        if sp:
            exit_plan_dict["t1"] = sp.get("T1")
            exit_plan_dict["t2"] = sp.get("T2")
            exit_plan_dict["t3"] = sp.get("T3")
            exit_plan_dict["stop"] = sp.get("stop_hint_price")
        missing_ep = (ep.get("missing_fields") or []) if isinstance(ep, dict) else []
        has_any_level = any((exit_plan_dict.get("t1"), exit_plan_dict.get("t2"), exit_plan_dict.get("stop")))
        if not has_any_level:
            exit_plan_dict["status"] = "NOT_AVAILABLE"
            exit_plan_dict["reason"] = "Exit plan not computed: " + ", ".join(missing_ep) if missing_ep else "Missing inputs (resistance_level, support_level, or ATR14)."
        else:
            exit_plan_dict["status"] = "AVAILABLE"
    except Exception as e:
        exit_plan_dict["status"] = "NOT_AVAILABLE"
        exit_plan_dict["reason"] = f"Exit plan error: {e}"
    lg = getattr(sr, "liquidity_gates", None) or {}
    underlying_liq = lg.get("underlying") or {}
    option_liq = lg.get("option") or {}
    risk_flags = {
        "earnings_days": getattr(sr, "earnings_days", None),
        "earnings_block": getattr(sr, "earnings_blocked", None),
        "stock_liq": underlying_liq.get("ok") if isinstance(underlying_liq, dict) else getattr(sr, "liquidity_ok", None),
        "option_liq": option_liq.get("ok") if isinstance(option_liq, dict) else getattr(sr, "liquidity_ok", None),
        "data_status": "OK" if (getattr(sr, "data_completeness", 0) or 0) >= 0.75 else "WARN",
        "missing_required": getattr(sr, "missing_fields", []) or [],
    }
    sel_el = getattr(sr, "symbol_eligibility", None) or {}
    expl_regime = (el.get("regime") or getattr(sr, "regime", "") or "").strip() or None
    support = technicals.get("support_level")
    support_cond = None
    if support is not None and isinstance(support, (int, float)):
        support_cond = f"Support ${float(support):.2f}" + (f" vs spot ${float(spot):.2f}" if spot else "")
    liq_ok = getattr(sr, "liquidity_ok", False)
    liq_reason = getattr(sr, "liquidity_reason", "") or ""
    explanation = {
        "stock_regime_reason": expl_regime,
        "support_condition": support_cond,
        "liquidity_condition": "OK" if liq_ok else (liq_reason or "Liquidity failed"),
        "iv_condition": getattr(sr, "primary_reason", None),
    }
    stock = {
        "price": getattr(sr, "price", None),
        "bid": getattr(sr, "bid", None),
        "ask": getattr(sr, "ask", None),
        "volume": getattr(sr, "volume", None),
        "avg_option_volume_20d": getattr(sr, "avg_option_volume_20d", None),
        "avg_stock_volume_20d": getattr(sr, "avg_stock_volume_20d", None),
        "quote_as_of": getattr(sr, "quote_date", None),
    }
    symbol_eligibility = {
        "status": sel_el.get("status", "UNKNOWN"),
        "required_data_missing": sel_el.get("required_data_missing", sel_el.get("reasons", [])) or [],
        "required_data_stale": sel_el.get("required_data_stale", []) or [],
        "reasons": sel_el.get("reasons", []) or [],
    }
    stage2 = getattr(sr, "stage2", None)
    chain_missing = list(getattr(stage2, "chain_missing_fields", None) or [])
    liquidity = {
        "stock_liquidity_ok": getattr(sr, "liquidity_ok", None),
        "option_liquidity_ok": getattr(sr, "liquidity_ok", None),
        "reason": getattr(sr, "liquidity_reason", None),
        "missing_fields": list(getattr(sr, "missing_fields", None) or []),
        "chain_missing_fields": chain_missing,
    }
    cap_hint = getattr(sr, "capital_hint", None)
    if isinstance(cap_hint, dict):
        suggested_pct = cap_hint.get("suggested_capital_pct")
    else:
        suggested_pct = getattr(cap_hint, "suggested_capital_pct", None) if cap_hint else None
    exp_count = 0
    contracts_count = None
    if st2:
        exp_count = st2.get("expirations_available", 0) or 0
        contracts_count = st2.get("contracts_evaluated")
    options = {
        "expirations_count": exp_count,
        "contracts_count": contracts_count,
        "underlying_price": spot,
    }
    top_rej = getattr(sr, "top_rejection_reasons", None) or {}
    sample_rejected_due_to_delta = top_rej.get("sample_rejected_due_to_delta") or []
    return SymbolDiagnosticsDetails(
        technicals=technicals,
        exit_plan=exit_plan_dict,
        risk_flags=risk_flags,
        explanation=explanation,
        stock=stock,
        symbol_eligibility=symbol_eligibility,
        liquidity=liquidity,
        score_breakdown=getattr(sr, "score_breakdown", None),
        rank_reasons=getattr(sr, "rank_reasons", None),
        suggested_capital_pct=suggested_pct,
        regime=getattr(sr, "regime", None),
        options=options,
        reasons_explained=None,  # never persisted; computed on-demand in API
        sample_rejected_due_to_delta=sample_rejected_due_to_delta,
    )


def _build_symbol_data_from_staged(
    sr: Any,
    sym_upper: str,
    ts: str,
) -> tuple[SymbolEvalSummary, List[CandidateRow], List[GateEvaluation], EarningsInfo]:
    """Build v2 structures from one staged SymbolEvaluationResult."""
    verdict = str(getattr(sr, "verdict", "HOLD") or "HOLD").upper()
    if verdict not in ("ELIGIBLE", "HOLD", "BLOCKED", "NOT_EVALUATED"):
        verdict = "HOLD"
    score = getattr(sr, "score", None)
    band = assign_band(score)
    stage_reached = getattr(sr, "stage_reached", None)
    stage_reached_val = getattr(stage_reached, "value", str(stage_reached) or "STAGE1_ONLY")
    stage2_ran = stage_reached_val == "STAGE2_CHAIN"

    cds = getattr(sr, "candidate_trades", []) or []
    sc = getattr(sr, "selected_contract", None)
    contract_d = (sc.get("contract") or sc) if sc and isinstance(sc, dict) else {}
    cand_list: List[CandidateRow] = []
    for i, ct in enumerate(cds):
        ct_dict = asdict(ct) if hasattr(ct, "__dataclass_fields__") else (ct if isinstance(ct, dict) else {})
        strat = str(ct_dict.get("strategy", "CSP"))
        exp = ct_dict.get("expiry")
        st = ct_dict.get("strike")
        _opt_sym = contract_d.get("option_symbol") if isinstance(contract_d, dict) and i == 0 else None
        _ct_key = f"{st}-{str(exp)[:10]}-{'PUT' if (strat or 'CSP').upper() == 'CSP' else 'CALL'}" if (st is not None and exp) else None
        cand_list.append(CandidateRow(
            symbol=sym_upper,
            strategy=strat,
            expiry=exp,
            strike=st,
            delta=ct_dict.get("delta"),
            credit_estimate=ct_dict.get("credit_estimate"),
            max_loss=ct_dict.get("max_loss"),
            why_this_trade=ct_dict.get("why_this_trade"),
            contract_key=_ct_key if i == 0 else None,
            option_symbol=_opt_sym if i == 0 else None,
        ))

    sc = getattr(sr, "selected_contract", None)
    strategy_val = None
    expiry_val = getattr(sr, "selected_expiration", None)
    if expiry_val and hasattr(expiry_val, "isoformat"):
        expiry_val = str(expiry_val.isoformat())[:10]
    elif expiry_val:
        expiry_val = str(expiry_val)[:10]

    gates: List[GateEvaluation] = []
    for g in getattr(sr, "gates", []) or []:
        if isinstance(g, dict):
            gates.append(GateEvaluation(
                name=g.get("name", ""),
                status=g.get("status", "SKIP"),
                reason=g.get("reason"),
            ))

    earnings = EarningsInfo(
        earnings_days=getattr(sr, "earnings_days", None),
        earnings_block=getattr(sr, "earnings_blocked", None),
        note="Not evaluated" if not getattr(sr, "earnings_days", None) and not getattr(sr, "earnings_blocked", None) else None,
    )

    stage1_status = "PASS" if stage_reached_val in ("STAGE1_ONLY", "STAGE2_CHAIN") else "FAIL"
    stage2_status = "PASS" if (stage2_ran and getattr(sr, "liquidity_ok", False)) else ("FAIL" if stage2_ran else "NOT_RUN")
    provider_ok = (getattr(sr, "data_completeness", 0) or 0) >= 0.75
    provider_status = "OK" if provider_ok else "WARN"

    if verdict == "ELIGIBLE":
        if sc and isinstance(sc, dict):
            strategy_val = str(sc.get("strategy", "CSP"))
            expiry_val = expiry_val or str(sc.get("expiration", "") or sc.get("expiry", ""))[:10]
        elif cds:
            first = cds[0]
            ft = asdict(first) if hasattr(first, "__dataclass_fields__") else (first if isinstance(first, dict) else {})
            strategy_val = str(ft.get("strategy", "CSP"))
            expiry_val = expiry_val or str(ft.get("expiry") or ft.get("expiration") or "")[:10]

    sc = getattr(sr, "selected_contract", None)
    max_loss_val: Optional[float] = sc.get("max_loss") if sc and isinstance(sc, dict) else None
    if max_loss_val is None and cds:
        first_ct = asdict(cds[0]) if hasattr(cds[0], "__dataclass_fields__") else (cds[0] if isinstance(cds[0], dict) else {})
        max_loss_val = first_ct.get("max_loss")
    price_val = getattr(sr, "price", None)
    capital_req: Optional[float] = max_loss_val if max_loss_val is not None else (price_val * 100 if price_val and price_val > 0 else None)
    expected_cr: Optional[float] = sc.get("credit_estimate") if sc and isinstance(sc, dict) else None
    if expected_cr is None and cds:
        first_ct = asdict(cds[0]) if hasattr(cds[0], "__dataclass_fields__") else (cds[0] if isinstance(cds[0], dict) else {})
        expected_cr = first_ct.get("credit_estimate")
    prem_yield: Optional[float] = (expected_cr / capital_req * 100) if capital_req and capital_req > 0 and expected_cr is not None else None
    mcap: Optional[float] = getattr(sr, "market_cap", None)
    rk = compute_rank_score(band, float(score) if score is not None else None, prem_yield, capital_req, mcap)
    summary = SymbolEvalSummary(
        symbol=sym_upper,
        verdict=verdict,
        final_verdict=verdict,
        score=score,
        band=band,
        primary_reason=getattr(sr, "primary_reason", None) or "",
        stage_status="RUN",
        stage1_status=stage1_status,
        stage2_status=stage2_status,
        provider_status=provider_status,
        data_freshness=getattr(sr, "quote_date", None) or getattr(sr, "fetched_at", None),
        evaluated_at=getattr(sr, "fetched_at", None) or ts,
        strategy=strategy_val,
        price=price_val,
        expiration=expiry_val,
        has_candidates=len(cds) > 0,
        candidate_count=len(cds),
        score_breakdown=getattr(sr, "score_breakdown", None),
        band_reason=assign_band_reason(score),  # from score only, never verdict
        max_loss=max_loss_val,
        underlying_price=price_val,
        capital_required=capital_req,
        expected_credit=expected_cr,
        premium_yield_pct=prem_yield,
        market_cap=mcap,
        rank_score=rk,
    )
    return summary, cand_list, gates, earnings


def evaluate_single_symbol_and_merge(symbol: str, mode: str = "LIVE") -> DecisionArtifactV2:
    """
    Run staged evaluation for one symbol and merge into the current store artifact.
    Updates store, returns the merged artifact.
    """
    from app.core.eval.universe_evaluator import run_universe_evaluation_staged
    from app.market.market_hours import get_market_phase

    ts = datetime.now(timezone.utc).isoformat()
    phase = get_market_phase() or "UNKNOWN"
    sym_upper = symbol.strip().upper()
    if not sym_upper:
        raise ValueError("symbol required")

    result = run_universe_evaluation_staged([sym_upper], use_staged=True)
    staged_symbols = getattr(result, "symbols", []) or []
    sr = next((s for s in staged_symbols if (getattr(s, "symbol", "") or "").strip().upper() == sym_upper), None)

    store = get_evaluation_store_v2()
    current = store.get_latest()

    _empty: Dict[str, Any] = {}
    if sr is None:
        summary = SymbolEvalSummary(
            symbol=sym_upper,
            verdict="NOT_EVALUATED",
            final_verdict="NOT_EVALUATED",
            score=None,
            band="D",
            primary_reason="Not evaluated",
            stage_status="NOT_RUN",
            stage1_status="NOT_RUN",
            stage2_status="NOT_RUN",
            provider_status=None,
            data_freshness=None,
            evaluated_at=None,
            strategy=None,
            price=None,
            expiration=None,
            has_candidates=False,
            candidate_count=0,
        )
        cand_list: List[CandidateRow] = []
        gates: List[GateEvaluation] = []
        earnings = EarningsInfo(None, None, "Not evaluated")
        diagnostics_details = SymbolDiagnosticsDetails(
            technicals=_empty,
            exit_plan={"t1": None, "t2": None, "t3": None, "stop": None},
            risk_flags=_empty,
            explanation=_empty,
            stock=_empty,
            symbol_eligibility=_empty,
            liquidity=_empty,
        )
    else:
        summary, cand_list, gates, earnings = _build_symbol_data_from_staged(sr, sym_upper, ts)
        diagnostics_details = _build_diagnostics_details(sr, sym_upper, ts)

    if current is None:
        run_id_val = str(uuid.uuid4())
        metadata = {
            "artifact_version": "v2",
            "mode": mode,
            "pipeline_timestamp": ts,
            "evaluation_timestamp_utc": ts,
            "run_id": run_id_val,
            "market_phase": phase,
            "universe_size": 1,
            "evaluated_count_stage1": 1 if sr else 0,
            "evaluated_count_stage2": 1 if (sr and getattr(sr, "stage_reached", None) and str(getattr(sr, "stage_reached", "")) == "STAGE2_CHAIN") else 0,
            "eligible_count": 1 if (summary.verdict == "ELIGIBLE") else 0,
            "warnings": [],
        }
        selected = []
        if summary.verdict == "ELIGIBLE" and cand_list:
            selected = [cand_list[0]] if cand_list else []
        merged = DecisionArtifactV2(
            metadata=metadata,
            symbols=[summary],
            selected_candidates=selected,
            candidates_by_symbol={sym_upper: cand_list},
            gates_by_symbol={sym_upper: gates},
            earnings_by_symbol={sym_upper: earnings},
            diagnostics_by_symbol={sym_upper: diagnostics_details},
            warnings=[],
        )
    else:
        symbols_list = list(current.symbols)
        idx = next((i for i, s in enumerate(symbols_list) if (s.symbol or "").strip().upper() == sym_upper), None)
        if idx is not None:
            symbols_list[idx] = summary
        else:
            symbols_list.append(summary)

        candidates_by_symbol = dict(current.candidates_by_symbol)
        candidates_by_symbol[sym_upper] = cand_list

        gates_by_symbol = dict(current.gates_by_symbol)
        gates_by_symbol[sym_upper] = gates

        earnings_by_symbol = dict(current.earnings_by_symbol)
        earnings_by_symbol[sym_upper] = earnings

        diagnostics_by_symbol = dict(current.diagnostics_by_symbol)
        diagnostics_by_symbol[sym_upper] = diagnostics_details

        selected = [c for c in current.selected_candidates if (c.symbol or "").strip().upper() != sym_upper]
        if summary.verdict == "ELIGIBLE" and cand_list:
            selected.append(cand_list[0])

        meta = dict(current.metadata)
        meta["pipeline_timestamp"] = ts
        meta["evaluation_timestamp_utc"] = ts
        meta["run_id"] = str(uuid.uuid4())
        meta["eligible_count"] = len([s for s in symbols_list if s.verdict == "ELIGIBLE"])

        merged = DecisionArtifactV2(
            metadata=meta,
            symbols=symbols_list,
            selected_candidates=selected,
            candidates_by_symbol=candidates_by_symbol,
            gates_by_symbol=gates_by_symbol,
            earnings_by_symbol=earnings_by_symbol,
            diagnostics_by_symbol=diagnostics_by_symbol,
            warnings=current.warnings,
        )

    store.set_latest(merged)
    logger.info("[EVAL_SVC_V2] evaluate_single_symbol_and_merge: %s merged", sym_upper)
    return merged
