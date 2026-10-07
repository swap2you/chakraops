# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R68 deepen grounded advisor — explain why-no-trade, compare strategies, teach."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.advisor.education_corpus_r68 import get_education_topic, list_education_stubs
from app.core.advisor.grounding_r58 import ALLOWED_GROUNDED_SOURCES, build_grounded_answer


INJECTION_MARKERS = (
    "ignore previous",
    "ignore all instructions",
    "system prompt",
    "reveal your prompt",
    "disable safety",
    "place order",
    "execute trade",
    "call robinhood write",
)

_INVENTED_BALANCE_RE = re.compile(
    r"(\$\s*[\d,]+(?:\.\d+)?|\b(?:cash|balance|buying power|equity)\s+(?:is|of|=)\s*[\d,]+)",
    re.IGNORECASE,
)


def detect_prompt_injection(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in INJECTION_MARKERS)


def _looks_like_invented_balance(text: str) -> bool:
    return bool(_INVENTED_BALANCE_RE.search(text or ""))


def _server_compose_ask_answer(question: str, citations: List[Dict[str, Any]]) -> str:
    """Never echo client free-text; compose a citation-bounded advisory stub."""
    refs = "; ".join(
        f"{c.get('source')}:{c.get('ref')}"
        for c in (citations or [])
        if isinstance(c, dict) and c.get("source")
    )
    return (
        f"Grounded advisory for: {(question or '').strip() or 'n/a'}. "
        f"Evidence limited to citations ({refs or 'none'}). "
        "Verify live balances only via broker snapshot / Portfolio APIs — "
        "do not treat this text as an account statement. "
        "Advisory only; manual_only; no trade execution."
    )


def explain_why_no_trade(
    *,
    reasons: List[str],
    citations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Grounded explanation for Stay in Cash / no-trade."""
    cite = citations or [
        {
            "source": "operator_docs",
            "ref": "stay_in_cash_policy",
            "as_of": None,
        }
    ]
    answer = "No trade / Stay in Cash because: " + ("; ".join(reasons) if reasons else "insufficient evidence.")
    out = build_grounded_answer(
        question="Why no trade?",
        citations=cite,
        answer=answer,
        confidence="medium",
        trust_client_answer=True,
    )
    out["why_no_trade"] = True
    out["reasons"] = list(reasons or [])
    return out


def compare_strategies(
    *,
    left: str,
    right: str,
    citations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compare two strategy labels with grounding — no return promises."""
    cite = citations or [
        {"source": "education_corpus", "ref": f"compare:{left}:{right}", "as_of": None}
    ]
    answer = (
        f"Compare {left} vs {right}: differences in collateral, assignment, and payoff shape. "
        "Neither side promises a return. Prefer Stay in Cash when data is weak."
    )
    out = build_grounded_answer(
        question=f"Compare {left} vs {right}",
        citations=cite,
        answer=answer,
        confidence="low",
        trust_client_answer=True,
    )
    out["comparison"] = {"left": left, "right": right}
    out["promises_returns"] = False
    return out


def deepen_ask(
    *,
    question: str,
    citations: List[Dict[str, Any]],
    answer: str = "",
    confidence: str = "low",
    mode: str = "ask",  # ask|why_no_trade|compare|teach
    teach_topic: Optional[str] = None,
    compare_left: Optional[str] = None,
    compare_right: Optional[str] = None,
    no_trade_reasons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Extended grounded ask with safety + education modes."""
    if detect_prompt_injection(question) or detect_prompt_injection(answer):
        return {
            "ok": False,
            "error": "prompt_injection_refused",
            "message": "Request refused by advisor safety policy.",
            "manual_only": True,
            "trade_execution": False,
            "broker_writes": False,
        }

    m = (mode or "ask").lower()
    if m == "why_no_trade":
        return explain_why_no_trade(reasons=list(no_trade_reasons or []), citations=citations or None)
    if m == "compare":
        return compare_strategies(
            left=str(compare_left or "CSP"),
            right=str(compare_right or "CC"),
            citations=citations or None,
        )
    if m == "teach":
        topic = get_education_topic(str(teach_topic or "delta"))
        if not topic.get("ok"):
            return {
                "ok": False,
                "error": "unknown_topic",
                "manual_only": True,
                "trade_execution": False,
                **topic,
            }
        teach_cites = citations or [
            {"source": "education_corpus", "ref": topic["id"], "as_of": None}
        ]
        return build_grounded_answer(
            question=question or f"Teach {topic['id']}",
            citations=teach_cites,
            answer=f"{topic['title']}: {topic['summary']}",
            confidence="medium",
            trust_client_answer=True,
        )

    # Default ask — server synthesizes; ignore client prose.
    _ = ALLOWED_GROUNDED_SOURCES
    return build_grounded_answer(
        question=question,
        citations=citations,
        answer="",
        confidence=confidence,
        trust_client_answer=False,
    )


def education_catalog() -> Dict[str, Any]:
    return list_education_stubs()
