#!/usr/bin/env python3
"""
Phase 3: Standalone, in-memory Market Regime Engine.

Learning and validation only. NOT wired into the app. No imports from app/, db,
dashboard, heartbeat, or CSP code. Accepts normalized inputs from REALTIME
(thetadata_capabilities output) or SNAPSHOT (manually constructed). Returns
regime (RISK_ON | RISK_OFF | NEUTRAL), confidence, and an explainable inputs
summary. Simple, explicit scoring; no ML.
"""

from __future__ import annotations

from typing import Any


# --- Scoring mapping (explicit, no ML) ---
# price_trend: +1 bullish, 0 neutral, -1 bearish
_PRICE_TREND_SCORE = {"bullish": 1, "neutral": 0, "bearish": -1}

# volatility: +1 low/contained, 0 moderate, -1 high
_VOLATILITY_SCORE = {"low": 1, "moderate": 0, "contained": 1, "high": -1}

# liquidity: +1 normal, 0 mixed, -1 thin/unreliable
_LIQUIDITY_SCORE = {"normal": 1, "mixed": 0, "thin": -1, "unreliable": -1}

# breadth (optional; not used in score per spec, but surfaced in output)
_BREADTH_VALUES = ("broad", "narrow", "mixed", "unavailable")


def _safe_get(d: dict[str, Any], key: str, default: Any = None) -> Any:
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


def _normalize_signal(val: Any) -> str:
    if val is None:
        return "unavailable"
    s = str(val).strip().lower()
    return s if s else "unavailable"


def compute_market_regime(inputs: dict[str, Any]) -> dict[str, Any]:
    """
    Compute market regime from a normalized inputs structure.

    inputs may come from:
      - REALTIME: derived from thetadata_capabilities output
      - SNAPSHOT: manually constructed

    Expected input keys (all optional; missing reduces max score and adds notes):
      - source: "REALTIME" | "SNAPSHOT"
      - health: "PASS" | "WARN" | "FAIL" (for REALTIME; used to downgrade confidence)
      - price_trend: "bullish" | "neutral" | "bearish"
      - volatility: "low" | "moderate" | "high" | "contained"
      - breadth: "broad" | "narrow" | "mixed" | "unavailable" (surfaced only)
      - liquidity: "normal" | "mixed" | "thin" | "unreliable"
      - notes: list (merged with engine notes)

    Returns exactly:
      - regime: "RISK_ON" | "RISK_OFF" | "NEUTRAL"
      - confidence: float in [0.0, 1.0]
      - inputs: { price_trend, volatility, breadth, liquidity } (strings used)
      - source: from input or "UNKNOWN"
      - notes: list of strings
    """
    notes: list[str] = []
    source = _safe_get(inputs, "source") or "UNKNOWN"
    if source not in ("REALTIME", "SNAPSHOT"):
        source = "UNKNOWN"
        notes.append("source unknown; treating as SNAPSHOT for confidence cap")

    health = _safe_get(inputs, "health")
    price_trend_raw = _normalize_signal(_safe_get(inputs, "price_trend"))
    volatility_raw = _normalize_signal(_safe_get(inputs, "volatility"))
    breadth_raw = _normalize_signal(_safe_get(inputs, "breadth"))
    liquidity_raw = _normalize_signal(_safe_get(inputs, "liquidity"))

    # Resolve inputs dict for output (what we used or "unavailable")
    used_price = price_trend_raw if price_trend_raw in _PRICE_TREND_SCORE else "unavailable"
    used_vol = volatility_raw if volatility_raw in _VOLATILITY_SCORE else "unavailable"
    used_breadth = breadth_raw if breadth_raw in _BREADTH_VALUES else "unavailable"
    used_liq = liquidity_raw if liquidity_raw in _LIQUIDITY_SCORE else "unavailable"

    if price_trend_raw not in _PRICE_TREND_SCORE and price_trend_raw != "unavailable":
        notes.append("price_trend value not recognized; treated as unavailable")
    if volatility_raw not in _VOLATILITY_SCORE and volatility_raw != "unavailable":
        notes.append("volatility value not recognized; treated as unavailable")
    if liquidity_raw not in _LIQUIDITY_SCORE and liquidity_raw != "unavailable":
        notes.append("liquidity value not recognized; treated as unavailable")

    # Scores (only from available signals)
    price_trend_score = _PRICE_TREND_SCORE.get(used_price)
    volatility_score = _VOLATILITY_SCORE.get(used_vol)
    liquidity_score = _LIQUIDITY_SCORE.get(used_liq)

    if used_price == "unavailable":
        notes.append("price_trend unavailable")
        price_trend_score = None
    if used_vol == "unavailable":
        notes.append("volatility unavailable")
        volatility_score = None
    if used_liq == "unavailable":
        notes.append("liquidity unavailable")
        liquidity_score = None

    scores = [s for s in (price_trend_score, volatility_score, liquidity_score) if s is not None]
    total_score = sum(scores)
    max_possible = len(scores)  # each signal ±1
    if max_possible == 0:
        total_score = 0
        regime = "NEUTRAL"
        base_confidence = 0.0
        notes.append("no signals available; defaulting to NEUTRAL")
    else:
        if total_score >= 2:
            regime = "RISK_ON"
        elif total_score <= -2:
            regime = "RISK_OFF"
        else:
            regime = "NEUTRAL"
        base_confidence = abs(total_score) / max_possible

    # Confidence adjustments
    confidence = base_confidence
    if max_possible > 0:
        if source == "REALTIME" and health == "WARN":
            confidence *= 0.7
            notes.append("realtime health WARN; confidence downgraded")
        if source == "SNAPSHOT":
            confidence = min(confidence, 0.85)
    confidence = max(0.0, min(1.0, round(confidence, 4)))

    # REALTIME FAIL: should not be used for regime
    if source == "REALTIME" and health == "FAIL":
        notes.append("realtime health FAIL; regime should not be used for decisions")
        confidence = 0.0

    # Merge incoming notes
    incoming = _safe_get(inputs, "notes")
    if isinstance(incoming, list):
        for n in incoming:
            if isinstance(n, str) and n.strip():
                notes.append(n.strip())

    return {
        "regime": regime,
        "confidence": confidence,
        "inputs": {
            "price_trend": used_price,
            "volatility": used_vol,
            "breadth": used_breadth,
            "liquidity": used_liq,
        },
        "source": source,
        "notes": notes,
    }


def _main() -> None:
    """CLI test harness: run 2–3 hardcoded examples and print regime dicts."""
    import json

    examples = [
        {
            "label": "REALTIME PASS (bullish)",
            "inputs": {
                "source": "REALTIME",
                "health": "PASS",
                "price_trend": "bullish",
                "volatility": "low",
                "breadth": "broad",
                "liquidity": "normal",
            },
        },
        {
            "label": "REALTIME FAIL (should not be used)",
            "inputs": {
                "source": "REALTIME",
                "health": "FAIL",
                "price_trend": "bearish",
                "volatility": "high",
                "liquidity": "thin",
            },
        },
        {
            "label": "SNAPSHOT fallback",
            "inputs": {
                "source": "SNAPSHOT",
                "price_trend": "neutral",
                "volatility": "moderate",
                "breadth": "mixed",
                "liquidity": "normal",
                "notes": ["using snapshot fallback"],
            },
        },
    ]

    print("Market Regime Engine — Phase 3 (validation only)\n")
    for ex in examples:
        label = ex["label"]
        inp = ex["inputs"]
        out = compute_market_regime(inp)
        print(f"--- {label} ---")
        print(json.dumps(out, indent=2, default=str))
        print()


if __name__ == "__main__":
    _main()
