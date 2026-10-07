# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R58 grounded AI advisor helpers — citations required; no broker writes."""

from __future__ import annotations

import re
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

# Client-supplied narrative must not invent monetary claims outside citation refs.
_MONEY_RE = re.compile(r"\$\s*[\d,]+(?:\.\d+)?|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b")


def _citation_blob(citations: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for c in citations:
        parts.append(str(c.get("ref") or ""))
        parts.append(str(c.get("source") or ""))
        if c.get("as_of") is not None:
            parts.append(str(c.get("as_of")))
    return " ".join(parts)


def _client_answer_invents_money(answer: str, citations: List[Dict[str, Any]]) -> bool:
    """True when answer contains monetary tokens not present in citation refs."""
    text = (answer or "").strip()
    if not text:
        return False
    blob = _citation_blob(citations)
    for m in _MONEY_RE.finditer(text):
        token = m.group(0).replace(" ", "")
        digits = re.sub(r"[^\d.]", "", token)
        if not digits:
            continue
        if digits not in blob and token not in blob:
            return True
    return False


def synthesize_grounded_answer(question: str, citations: List[Dict[str, Any]]) -> str:
    """Server-authored answer from citations only — never trusts client prose."""
    refs = ", ".join(f"{c.get('source')}:{c.get('ref')}" for c in citations) or "none"
    q = (question or "").strip() or "unspecified"
    return (
        f"Grounded advisory note for “{q}”. Evidence is limited to cited sources ({refs}). "
        "Balances and holdings must come from broker_snapshot citations — never invent figures. "
        "Stay in Cash remains valid when evidence is weak. Manual execution only; no broker writes."
    )


def build_grounded_answer(
    *,
    question: str,
    citations: List[Dict[str, Any]],
    answer: str = "",
    confidence: str = "low",
    trust_client_answer: bool = False,
) -> Dict[str, Any]:
    """Fail closed when citations missing or from unknown sources.

    By default the server synthesizes the answer from citations and ignores
    client-supplied prose (R70-DEF-060). When ``trust_client_answer`` is True
    (internal deepen/teach helpers), the answer is still refused if it invents
    monetary amounts absent from citation refs.
    """
    q = (question or "").strip()
    if not q:
        return {
            "ok": False,
            "error": "question_required",
            "last_error_code": "QUESTION_REQUIRED",
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
            "last_error_code": "UNGROUNDED_REFUSED",
            "message": "Advisor refuses to answer without grounded citations.",
            "manual_only": True,
            "trade_execution": False,
            "broker_writes": False,
        }

    if trust_client_answer:
        client = (answer or "").strip()
        if client and _client_answer_invents_money(client, clean_cites):
            return {
                "ok": False,
                "error": "invented_values_refused",
                "last_error_code": "INVENTED_VALUES_REFUSED",
                "message": "Advisor refuses answers that invent monetary values not present in citations.",
                "manual_only": True,
                "trade_execution": False,
                "broker_writes": False,
            }
        final_answer = client or synthesize_grounded_answer(q, clean_cites)
        answer_source = "client_verified" if client else "server_synthesized"
    else:
        final_answer = synthesize_grounded_answer(q, clean_cites)
        answer_source = "server_synthesized"

    return {
        "ok": True,
        "question": q,
        "answer": final_answer,
        "answer_source": answer_source,
        "citations": clean_cites,
        "confidence": confidence,
        "last_error_code": None,
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
