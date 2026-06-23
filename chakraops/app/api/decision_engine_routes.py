# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Advisory decision-engine API (R33.0).

- ``GET  /decision-engine/profiles`` returns the canonical strategy profiles.
- ``POST /decision-engine/evaluate`` ranks caller-supplied, freshness-stamped
  candidates into actionable / watch / blocked / stay-in-cash advice.

The evaluate endpoint is deterministic and side-effect free: it computes only
from the JSON the caller supplies (no network, no ORATS calls, no order
routing). Every result is advisory and labeled manual-only. Mounted under the
public ``/api/ui`` prefix.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class OptionContractModel(BaseModel):
    delta: float
    dte: int
    premium: float
    strike: float
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    bid_ask_spread_pct: Optional[float] = None


class CandidateModel(BaseModel):
    symbol: str
    strategy: str
    market_regime: str
    price: Optional[float] = None
    iv_rank: Optional[float] = None
    price_as_of: Optional[str] = None
    chain_as_of: Optional[str] = None
    earnings_days: Optional[int] = None
    contract: Optional[OptionContractModel] = None
    shares_held: int = 0
    sector: Optional[str] = None


class PortfolioModel(BaseModel):
    total_value: float
    available_cash: float
    symbol_exposure: Dict[str, float] = Field(default_factory=dict)
    sector_exposure: Dict[str, float] = Field(default_factory=dict)


class EvaluateRequest(BaseModel):
    profile: str = "balanced"
    profile_overrides: Optional[Dict[str, Any]] = None
    portfolio: PortfolioModel
    candidates: List[CandidateModel] = Field(default_factory=list)


@router.get("/decision-engine/profiles")
def get_decision_profiles() -> dict:
    """Return all selectable canonical strategy profiles."""
    from app.core.decision_engine.profiles import list_profiles

    return {"profiles": list_profiles(), "manual_only": True}


@router.post("/decision-engine/evaluate")
def post_decision_evaluate(req: EvaluateRequest) -> dict:
    """Evaluate supplied candidates into ranked, advisory, manual-only output."""
    from app.core.decision_engine.contract import (
        DecisionInput,
        OptionContract,
        PortfolioState,
    )
    from app.core.decision_engine.engine import evaluate
    from app.core.decision_engine.profiles import ProfileValidationError

    portfolio = PortfolioState(
        total_value=req.portfolio.total_value,
        available_cash=req.portfolio.available_cash,
        symbol_exposure=dict(req.portfolio.symbol_exposure),
        sector_exposure=dict(req.portfolio.sector_exposure),
    )

    inputs: List[DecisionInput] = []
    for cand in req.candidates:
        contract = None
        if cand.contract is not None:
            contract = OptionContract(
                delta=cand.contract.delta,
                dte=cand.contract.dte,
                premium=cand.contract.premium,
                strike=cand.contract.strike,
                open_interest=cand.contract.open_interest,
                volume=cand.contract.volume,
                bid_ask_spread_pct=cand.contract.bid_ask_spread_pct,
            )
        inputs.append(
            DecisionInput(
                symbol=cand.symbol,
                strategy=cand.strategy,
                market_regime=cand.market_regime,
                price=cand.price,
                iv_rank=cand.iv_rank,
                price_as_of=cand.price_as_of,
                chain_as_of=cand.chain_as_of,
                earnings_days=cand.earnings_days,
                contract=contract,
                shares_held=cand.shares_held,
                sector=cand.sector,
            )
        )

    try:
        return evaluate(
            inputs,
            profile_name=req.profile,
            portfolio=portfolio,
            profile_overrides=req.profile_overrides,
        )
    except ProfileValidationError as exc:
        # Invalid profile name or profile_overrides is a client error, not a 500.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
