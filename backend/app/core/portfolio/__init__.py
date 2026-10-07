# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3: Portfolio & Risk Intelligence — summary, exposure, risk profile."""

from app.core.portfolio.models import ExposureItem, PortfolioSummary, RiskFlag, RiskProfile
from app.core.portfolio.store import load_risk_profile, save_risk_profile, update_risk_profile
from app.core.portfolio.service import compute_portfolio_summary, compute_exposure
from app.core.portfolio.risk import evaluate_risk_flags, would_exceed_limits
from app.core.portfolio.portfolio_snapshot import build_portfolio_snapshot, load_open_positions
from app.core.portfolio.portfolio_guardrails import apply_guardrails
from app.core.portfolio.assignment_stress_simulator import (
    format_stress_summary,
    format_stress_summary_dynamic,
    simulate_assignment_stress,
    simulate_assignment_stress_dynamic,
)

__all__ = [
    "ExposureItem",
    "PortfolioSummary",
    "RiskFlag",
    "RiskProfile",
    "load_risk_profile",
    "save_risk_profile",
    "update_risk_profile",
    "compute_portfolio_summary",
    "compute_exposure",
    "evaluate_risk_flags",
    "would_exceed_limits",
    "build_portfolio_snapshot",
    "load_open_positions",
    "apply_guardrails",
    "simulate_assignment_stress",
    "format_stress_summary",
    "simulate_assignment_stress_dynamic",
    "format_stress_summary_dynamic",
]
