# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R58 grounded AI advisor helpers — citations required; no broker writes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


ALLOWED_GROUNDED_SOURCES = frozenset(
    {
        "broker_snapshot",
        "orats",
        "journal",
        "decision_store",
        "universe",
        "operator_docs",
        "education_corpus",
    }
)


def build_grounded_answer(
    *,
    question: str,
    citations: List[Dict[str, Any]],
    answer: str,
    confidence: str = "low",
) -> Dict[str, Any]:
    """Fail closed when citations missing or from unknown sources."""
    q = (question or "").strip()
    if not q:
        return {
            "ok": False,
            "error": "question_required",
            "manual_only": True,
            "trade_execution": False,
        }
    clean_cites: List[Dict[str, Any]] = []
    for c in citations or []:
        if not isinstance(c, dict):
            continue
        src = str(c.get("source") or "").strip()
        if src not in ALLOWED_GROUNDED_SOURCES:
            continue
        clean_cites.append(
            {
                "source": src,
                "ref": str(c.get("ref") or "")[:200],
                "as_of": c.get("as_of"),
            }
        )
    if not clean_cites:
        return {
            "ok": False,
            "error": "ungrounded_refused",
            "message": "Advisor refuses to answer without grounded citations.",
            "manual_only": True,
            "trade_execution": False,
            "broker_writes": False,
        }
    return {
        "ok": True,
        "question": q,
        "answer": (answer or "").strip() or "Insufficient grounded evidence.",
        "citations": clean_cites,
        "confidence": confidence,
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "disclaimer": "Advisory only. Manual execution. Not broker-routable.",
    }


def build_goal_plan(
    *,
    goal: str,
    horizon_months: int,
    constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Educational goal planner — never emits broker write instructions."""
    g = (goal or "").strip() or "unspecified"
    horizon = max(1, min(int(horizon_months or 12), 120))
    constraints = constraints or {}
    steps = [
        {
            "id": "inventory",
            "title": "Inventory accounts and risk budget",
            "detail": "Use broker read-only snapshot + journal; do not invent balances.",
        },
        {
            "id": "education",
            "title": "Complete education modules for the strategy",
            "detail": "Wheel/CSP education is not live advice.",
        },
        {
            "id": "paper",
            "title": "Paper/journal a sample size before capital",
            "detail": "Stay in Cash remains valid when data or thesis is weak.",
        },
        {
            "id": "manual",
            "title": "Execute manually only after ticket readiness",
            "detail": "No broker writes from ChakraOps; operator places orders in broker UI.",
        },
    ]
    return {
        "goal": g,
        "horizon_months": horizon,
        "constraints": constraints,
        "steps": steps,
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "disclaimer": "Goal plan is educational/advisory. Not an order.",
    }
