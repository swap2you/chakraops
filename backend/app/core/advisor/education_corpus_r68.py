# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R68 education content stubs for grounded advisor + Learn UI."""

from __future__ import annotations

from typing import Any, Dict, List


EDUCATION_TOPICS: Dict[str, Dict[str, str]] = {
    "delta": {
        "title": "Delta",
        "summary": "Approximate change in option price for a $1 move in the underlying.",
    },
    "dte": {
        "title": "DTE",
        "summary": "Days to expiration — time remaining until the option expires.",
    },
    "iv": {
        "title": "Implied Volatility (IV)",
        "summary": "Market's priced expectation of future volatility; not a return forecast.",
    },
    "iv_rank": {
        "title": "IV Rank",
        "summary": "Where current IV sits vs a lookback window; context only, not a trade signal alone.",
    },
    "theta": {
        "title": "Theta",
        "summary": "Time decay of an option's value, typically per day.",
    },
    "assignment": {
        "title": "Assignment",
        "summary": "Obligation to buy (short put) or sell (short call) shares when exercised against you.",
    },
    "cc": {
        "title": "Covered Call (CC)",
        "summary": "Long shares plus short call; caps upside, collects premium.",
    },
    "csp": {
        "title": "Cash-Secured Put (CSP)",
        "summary": "Short put with cash reserved for potential assignment.",
    },
    "stop_thesis_failure": {
        "title": "Stop / Thesis Failure",
        "summary": "Exit when the original reason for the trade is invalidated — not only on a price tick.",
    },
    "concentration": {
        "title": "Concentration",
        "summary": "How much of an account is tied to one symbol or sector; measured per account, never pooled.",
    },
    "hedging": {
        "title": "Hedging",
        "summary": "Reducing downside with puts, collars, or ETF overlays — advisory research only here.",
    },
    "backtest_limitations": {
        "title": "Backtest Limitations",
        "summary": "Backtests can miss fills, borrow, dividends, and regime shifts; never auto-promote thresholds.",
    },
}


def list_education_stubs() -> Dict[str, Any]:
    items: List[Dict[str, str]] = []
    for key, meta in EDUCATION_TOPICS.items():
        items.append({"id": key, "title": meta["title"], "summary": meta["summary"]})
    return {
        "schema": "education_corpus_r68",
        "source": "education_corpus",
        "items": items,
        "manual_only": True,
        "trade_execution": False,
        "disclaimer": "Education stubs only — not live trading advice.",
    }


def get_education_topic(topic_id: str) -> Dict[str, Any]:
    key = (topic_id or "").strip().lower().replace(" ", "_")
    meta = EDUCATION_TOPICS.get(key)
    if not meta:
        return {
            "ok": False,
            "error": "unknown_topic",
            "known": sorted(EDUCATION_TOPICS.keys()),
            "manual_only": True,
        }
    return {
        "ok": True,
        "id": key,
        "title": meta["title"],
        "summary": meta["summary"],
        "source": "education_corpus",
        "manual_only": True,
        "trade_execution": False,
    }
