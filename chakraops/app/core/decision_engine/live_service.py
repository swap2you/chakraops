# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Canonical live recommendation service (R34.0 — closes H-5).

Makes the canonical R33 decision engine the **authoritative producer** of the
primary live recommendation. It builds canonical ``DecisionInput`` objects from
the persisted v2 decision artifact (+ portfolio context), runs the canonical
engine (which wires the R32 ``stale_data_gate``), applies recommendation-set
capital safety, and returns one authoritative, manual-only result.

Design constraints honored:
- No new ORATS calls and no silent fallback provider: inputs come only from the
  already-persisted artifact + holdings.
- R33 strategy mathematics are NOT changed here.
- Per-contract liquidity is not stored in the artifact; the upstream batch
  Stage-2 gate exposes ``option_liquidity_ok``. When that flag is True the
  contract is treated as liquidity-validated upstream and tagged with the
  provenance reason ``LIQUIDITY_VALIDATED_UPSTREAM``. When it is False/unknown
  the contract's liquidity fields stay absent and the canonical engine blocks.
- Advisory and manual-only; nothing routes orders.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from app.core.decision_engine.contract import (
    COVERED_CALL,
    CSP,
    DecisionInput,
    OptionContract,
    PortfolioState,
    SHARE_BUY,
)
from app.core.decision_engine.engine import evaluate
from app.core.decision_engine.explanation import build_explanation
from app.core.decision_engine.legacy_adapter import DECISION_SOURCE, to_live_recommendations
from app.core.decision_engine.profiles import ProfileValidationError, get_profile

# Artifact strategy code -> canonical strategy.
_STRATEGY_MAP: Dict[str, str] = {
    "CSP": CSP,
    "CC": COVERED_CALL,
    "COVERED_CALL": COVERED_CALL,
    "STOCK": SHARE_BUY,
    "SHARE_BUY": SHARE_BUY,
    "SHARES": SHARE_BUY,
}

LIQUIDITY_VALIDATED_UPSTREAM = "LIQUIDITY_VALIDATED_UPSTREAM"


def _sector_for(symbol: str) -> Optional[str]:
    """Map a symbol to its sector from approved local company metadata.

    Returns ``None`` when the sector is unknown so the canonical engine can apply
    its safe sector policy (block incremental exposure) rather than guessing.
    """
    try:
        from app.core.market.company_data import get_company_metadata

        meta = get_company_metadata(symbol)
        sector = (meta or {}).get("sector") if meta else None
        sector = (sector or "").strip()
        return sector or None
    except Exception:
        return None


def _g(obj: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a dataclass-like object or a dict."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    s = str(value).strip()
    try:
        if "T" in s or " " in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _dte_from_expiration(expiration: Optional[str], now: datetime) -> Optional[int]:
    d = _parse_date(expiration)
    if d is None:
        return None
    return (d - now.date()).days


def _select_candidate_for_symbol(artifact: Any, symbol: str) -> Any:
    """Best candidate for a symbol: prefer selected_candidates, else first candidate."""
    for c in (_g(artifact, "selected_candidates", []) or []):
        if (_g(c, "symbol", "") or "").strip().upper() == symbol:
            return c
    by_sym = _g(artifact, "candidates_by_symbol", {}) or {}
    rows = by_sym.get(symbol) if isinstance(by_sym, Mapping) else None
    if rows:
        return rows[0]
    return None


def _option_contract_from(
    candidate: Any,
    summary: Any,
    diagnostics: Any,
    now: datetime,
) -> tuple[Optional[OptionContract], List[str]]:
    """Build an OptionContract from artifact data; returns (contract, provenance_codes)."""
    if candidate is None:
        return None, []
    strike = _g(candidate, "strike")
    delta = _g(candidate, "delta")
    credit = _g(candidate, "credit_estimate")
    if credit is None:
        credit = _g(summary, "expected_credit")
    premium = (float(credit) / 100.0) if credit is not None else None
    expiry = _g(candidate, "expiry") or _g(summary, "expiration")
    dte = _dte_from_expiration(expiry, now)

    if strike is None or delta is None or premium is None or dte is None:
        return None, []

    provenance: List[str] = []
    oi: Optional[int] = None
    volume: Optional[int] = None
    spread: Optional[float] = None

    liq = _g(diagnostics, "liquidity", {}) or {}
    option_liq_ok = _g(liq, "option_liquidity_ok")
    if option_liq_ok is True:
        # Liquidity was validated by the upstream batch Stage-2 gate. The artifact
        # does not persist per-contract OI/volume/spread, so we mark it validated
        # upstream (transparent provenance) rather than re-measure.
        oi, volume, spread = 1_000_000, 1_000_000, 0.0
        provenance.append(LIQUIDITY_VALIDATED_UPSTREAM)
    # else: leave None -> canonical liquidity_gate blocks with LIQUIDITY_DATA_MISSING

    return (
        OptionContract(
            delta=float(delta),
            dte=int(dte),
            premium=float(premium),
            strike=float(strike),
            open_interest=oi,
            volume=volume,
            bid_ask_spread_pct=spread,
        ),
        provenance,
    )


def build_decision_inputs_from_artifact(
    artifact: Any,
    *,
    shares_by_symbol: Optional[Mapping[str, int]] = None,
    now: Optional[datetime] = None,
    default_regime: str = "NEUTRAL",
) -> tuple[List[DecisionInput], Dict[str, List[str]]]:
    """Build canonical inputs from the persisted v2 artifact.

    Returns ``(inputs, provenance_by_symbol_strategy)`` where provenance records
    upstream-derived facts (e.g. liquidity validated by the batch gate).
    """
    now = now or datetime.now(timezone.utc)
    shares_by_symbol = shares_by_symbol or {}
    inputs: List[DecisionInput] = []
    provenance: Dict[str, List[str]] = {}

    earnings_by = _g(artifact, "earnings_by_symbol", {}) or {}
    diag_by = _g(artifact, "diagnostics_by_symbol", {}) or {}

    for summary in (_g(artifact, "symbols", []) or []):
        symbol = (_g(summary, "symbol", "") or "").strip().upper()
        if not symbol:
            continue
        strategy_code = (_g(summary, "strategy", "") or "").strip().upper()
        strategy = _STRATEGY_MAP.get(strategy_code)
        if strategy is None:
            continue

        price = _g(summary, "price")
        if price is None:
            price = _g(summary, "underlying_price")

        diagnostics = diag_by.get(symbol) if isinstance(diag_by, Mapping) else None
        regime = (_g(diagnostics, "regime") or default_regime or "NEUTRAL").upper()

        earnings = earnings_by.get(symbol) if isinstance(earnings_by, Mapping) else None
        earnings_days = _g(earnings, "earnings_days")

        as_of = _g(summary, "data_freshness") or _g(summary, "evaluated_at")

        contract = None
        prov: List[str] = []
        if strategy in (CSP, COVERED_CALL):
            candidate = _select_candidate_for_symbol(artifact, symbol)
            contract, prov = _option_contract_from(candidate, summary, diagnostics, now)

        inputs.append(
            DecisionInput(
                symbol=symbol,
                strategy=strategy,
                market_regime=regime,
                price=float(price) if price is not None else None,
                price_as_of=as_of,
                chain_as_of=as_of if strategy in (CSP, COVERED_CALL) else None,
                earnings_days=int(earnings_days) if earnings_days is not None else None,
                contract=contract,
                shares_held=int(shares_by_symbol.get(symbol, 0) or 0),
                sector=_sector_for(symbol),
            )
        )
        if prov:
            provenance[f"{symbol}:{strategy}"] = prov

    return inputs, provenance


def cash_is_known(
    guardrails_metrics: Optional[Mapping[str, Any]],
    guardrails_snapshot: Optional[Mapping[str, Any]],
) -> bool:
    """True only when an explicit available-cash figure is present.

    Total equity is never treated as available cash (R34.0 safety fix).
    """
    metrics = guardrails_metrics or {}
    snapshot = guardrails_snapshot or {}
    return snapshot.get("cash") is not None or metrics.get("cash") is not None


def portfolio_state_from_metrics(
    guardrails_metrics: Optional[Mapping[str, Any]],
    guardrails_snapshot: Optional[Mapping[str, Any]],
) -> PortfolioState:
    """Build a PortfolioState from the guardrails snapshot/metrics used by the live route.

    R34.0 fail-closed cash policy: available cash is NEVER inferred from total
    equity. When no explicit cash figure exists, ``available_cash`` is 0.0 so
    cash-consuming strategies (CSP / share buy) are blocked rather than sized
    against an assumed balance. Covered calls (which need owned shares, not cash)
    are unaffected.
    """
    metrics = guardrails_metrics or {}
    snapshot = guardrails_snapshot or {}
    total_value = (
        metrics.get("total_equity")
        or snapshot.get("total_equity")
        or 0.0
    )
    available_cash = (
        snapshot.get("cash")
        if snapshot.get("cash") is not None
        else metrics.get("cash")
    )
    if available_cash is None:
        # Fail-closed: unknown cash => not deployable. Do NOT infer from equity.
        available_cash = 0.0
    symbol_exposure = dict(metrics.get("symbol_notionals") or snapshot.get("symbol_notionals") or {})
    clean_symbol_exposure = {k: float(v) for k, v in symbol_exposure.items() if v is not None}
    # Derive existing sector exposure from the portfolio's per-symbol notionals so
    # the sector cap is enforced against live holdings (not silently skipped).
    sector_exposure: Dict[str, float] = {}
    for sym, val in clean_symbol_exposure.items():
        sec = _sector_for(sym)
        if sec:
            sector_exposure[sec] = sector_exposure.get(sec, 0.0) + float(val)
    return PortfolioState(
        total_value=float(total_value or 0.0),
        available_cash=float(available_cash or 0.0),
        symbol_exposure=clean_symbol_exposure,
        sector_exposure=sector_exposure,
    )


def compute_capital_set_safety(
    actionable_items: List[Dict[str, Any]],
    portfolio: PortfolioState,
    profile: Mapping[str, Any],
    *,
    cash_unknown: bool = False,
) -> Dict[str, Any]:
    """Recommendation-set capital safety for the displayed actionable set.

    Each recommendation is sized INDEPENDENTLY against the full portfolio, so the
    displayed quantities are NOT jointly executable. This computes the combined
    capital the displayed set would require and warns when it exceeds deployable
    capital after the profile cash buffer. Pure presentation safety; it does not
    change R33 sizing math.
    """
    cash_buffer_pct = float(profile.get("cash_buffer_pct", 0.0) or 0.0)
    buffer_amount = round(portfolio.total_value * cash_buffer_pct / 100.0, 2)
    deployable_capital = round(max(0.0, portfolio.available_cash - buffer_amount), 2)
    total_required = round(
        sum(float(i.get("capital_required") or 0.0) for i in actionable_items), 2
    )
    exceeds = total_required > deployable_capital
    flags: List[str] = []
    if exceeds:
        flags.append("RECOMMENDATION_SET_EXCEEDS_DEPLOYABLE_CAPITAL")
    if cash_unknown:
        # Cash-consuming strategies are blocked upstream; surface why explicitly.
        flags.append("AVAILABLE_CASH_UNKNOWN")
        flags.append("CASH_STRATEGIES_BLOCKED_PENDING_CASH_DATA")
    return {
        "per_suggestion_not_additive": True,
        "note_code": "PER_SUGGESTION_SIZED_INDEPENDENTLY_NOT_JOINTLY_EXECUTABLE",
        "total_capital_required_displayed": total_required,
        "available_cash": None if cash_unknown else round(portfolio.available_cash, 2),
        "cash_known": not cash_unknown,
        "cash_buffer_pct": cash_buffer_pct,
        "cash_buffer_amount": buffer_amount,
        "deployable_capital": deployable_capital,
        "exceeds_deployable_capital": exceeds,
        "flags": flags,
        "assumes_leverage_or_margin": False,
    }


def compute_live_recommendations(
    artifact: Any,
    *,
    profile_name: str = "balanced",
    portfolio: Optional[PortfolioState] = None,
    guardrails_metrics: Optional[Mapping[str, Any]] = None,
    guardrails_snapshot: Optional[Mapping[str, Any]] = None,
    shares_by_symbol: Optional[Mapping[str, int]] = None,
    now: Optional[datetime] = None,
    profile_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Authoritative live recommendation block produced by the canonical engine.

    Raises ``ProfileValidationError`` for an invalid profile / overrides (callers
    should map to HTTP 422). Returns a dict tagged ``decision_source ==
    'canonical_decision_engine'`` so the live API can declare it the single
    authoritative primary; the legacy stack must not produce a conflicting
    primary.
    """
    now = now or datetime.now(timezone.utc)
    cash_unknown = False
    if portfolio is None:
        cash_unknown = not cash_is_known(guardrails_metrics, guardrails_snapshot)
        portfolio = portfolio_state_from_metrics(guardrails_metrics, guardrails_snapshot)

    inputs, provenance = build_decision_inputs_from_artifact(
        artifact, shares_by_symbol=shares_by_symbol, now=now
    )

    # Validate the profile up front so callers can return a clean 422.
    profile_obj = get_profile(profile_name, overrides=dict(profile_overrides) if profile_overrides else None)

    result = evaluate(
        inputs,
        profile_name=profile_name,
        portfolio=portfolio,
        now=now,
        profile_overrides=dict(profile_overrides) if profile_overrides else None,
    )

    recommendations = to_live_recommendations(result)

    # Annotate liquidity provenance onto the matching actionable/watch items.
    for bucket in ("actionable", "watch"):
        for item in recommendations.get(bucket, []):
            key = f"{item.get('symbol')}:{item.get('strategy')}"
            extra = provenance.get(key)
            if extra:
                merged = list(dict.fromkeys(list(item.get("reason_codes") or []) + extra))
                item["reason_codes"] = merged

    # R36.1: attach the additive, behavior-preserving explainability contract.
    profile_dict = profile_obj.to_dict()
    for bucket in ("actionable", "watch", "blocked"):
        for item in recommendations.get(bucket, []):
            item["explanation"] = build_explanation(item, profile_dict)
    sic = recommendations.get("stay_in_cash")
    if isinstance(sic, dict):
        sic["explanation"] = build_explanation(sic, profile_dict)

    capital_safety = compute_capital_set_safety(
        recommendations.get("actionable", []),
        portfolio,
        profile_obj.to_dict(),
        cash_unknown=cash_unknown,
    )

    data_flags: List[str] = []
    if cash_unknown:
        data_flags.append("AVAILABLE_CASH_UNKNOWN")

    return {
        "decision_source": DECISION_SOURCE,
        "authoritative": True,
        "manual_only": True,
        "profile": profile_obj.to_dict(),
        "as_of_utc": result.get("as_of_utc"),
        "recommendations": recommendations,
        "capital_safety": capital_safety,
        "counts": result.get("counts"),
        "portfolio": portfolio.to_dict(),
        "cash_known": not cash_unknown,
        "data_flags": data_flags,
    }
