#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS proof run: fetch base chain + enriched strikes/options, emit sample PUTs.
No server dependency; no evaluator. Uses existing app pipeline (fetch_option_chain).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv
    load_dotenv(repo_root / ".env")
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="ORATS proof run: fetch chain + options, emit sample PUTs")
    parser.add_argument("--symbol", required=True, help="Underlying symbol (e.g. NVDA, SPY)")
    parser.add_argument("--dte_min", type=int, default=30, help="DTE min")
    parser.add_argument("--dte_max", type=int, default=45, help="DTE max")
    parser.add_argument("--mode", choices=("live", "delayed"), default="delayed", help="ORATS mode")
    parser.add_argument("--outdir", type=Path, default=repo_root / "artifacts" / "orats_harness", help="Output directory")
    args = parser.parse_args()

    symbol = args.symbol.strip().upper()
    out_dir = args.outdir
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{symbol}_{ts}.json"
    md_path = out_dir / f"{symbol}_{ts}.md"

    try:
        from app.core.options.orats_chain_pipeline import (
            fetch_option_chain,
            OratsOpraModeError,
            OratsChainError,
        )
    except ImportError as e:
        out = {"error": str(e), "symbol": symbol, "timestamp": ts}
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# ORATS harness run: {symbol}\n\n**Error:** {e}\n")
        return 1

    chain_mode = "DELAYED" if args.mode == "delayed" else "LIVE"
    try:
        result = fetch_option_chain(
            symbol,
            dte_min=args.dte_min,
            dte_max=args.dte_max,
            enrich_all=True,
            chain_mode=chain_mode,
            delta_lo=0.10,
            delta_hi=0.45,
        )
    except (OratsOpraModeError, OratsChainError) as e:
        out = {"error": str(e), "symbol": symbol, "timestamp": ts, "mode": args.mode}
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# ORATS harness run: {symbol}\n\n**Error:** {e}\n")
        return 1

    if result.error or not result.contracts:
        out = {
            "error": result.error or "No contracts",
            "symbol": symbol,
            "timestamp": ts,
            "mode": args.mode,
            "base_chain_count": result.base_chain_count,
            "opra_symbols_generated": result.opra_symbols_generated,
            "enriched_count": result.enriched_count,
            "strikes_options_telemetry": getattr(result, "strikes_options_telemetry", None),
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# ORATS harness run: {symbol}\n\n**Error:** {out['error']}\n")
        return 1

    puts = [c for c in result.contracts if getattr(c, "option_type", "") == "PUT"]
    underlying = result.underlying_price or 0
    # Sort by distance from ATM (strike vs underlying), take up to 50
    def key_otm(c):
        s = getattr(c, "strike", 0) or 0
        return abs(s - underlying)
    puts_sorted = sorted(puts, key=key_otm)[:50]

    # Proof stats: required per-contract = optionSymbol/opra, put/call, exp, strike, delta, bid, ask, open_interest
    def _has(v):
        return v is not None and (not isinstance(v, str) or v.strip() != "") and (not isinstance(v, (int, float)) or (v != 0 or v == 0))
    def _present(c, name):
        v = getattr(c, name, None)
        if name == "opra_symbol" and v is None:
            v = getattr(c, "option_symbol", None)
        return _has(v)
    puts_in_dte = len(puts)
    missing_bid = sum(1 for p in puts if not _present(p, "bid"))
    missing_ask = sum(1 for p in puts if not _present(p, "ask"))
    missing_oi = sum(1 for p in puts if not _present(p, "open_interest"))
    missing_delta = sum(1 for p in puts if not _present(p, "delta"))
    required_attrs = ("opra_symbol", "expiration", "strike", "delta", "bid", "ask", "open_interest")
    puts_with_required_fields = sum(
        1 for p in puts
        if all(_present(p, a) for a in required_attrs)
    )
    expirations_selected = sorted(set(getattr(p, "expiration", None) for p in puts if getattr(p, "expiration", None) is not None))
    expirations_selected = [e.isoformat()[:10] if hasattr(e, "isoformat") else str(e) for e in expirations_selected]

    rows = []
    for c in puts_sorted:
        strike = getattr(c, "strike", None)
        exp = getattr(c, "expiration", None)
        delta = getattr(c, "delta", None)
        bid = getattr(c, "bid", None)
        ask = getattr(c, "ask", None)
        oi = getattr(c, "open_interest", None)
        spread = (float(ask) - float(bid)) if (bid is not None and ask is not None) else None
        mid = (float(bid) + float(ask)) / 2 if (bid is not None and ask is not None) else None
        spread_pct = (spread / mid * 100) if (spread is not None and mid and mid > 0) else None
        rows.append({
            "option_symbol": getattr(c, "opra_symbol", ""),
            "expiration": exp.isoformat() if exp else None,
            "strike": strike,
            "delta": delta,
            "bid": bid,
            "ask": ask,
            "open_interest": oi,
            "spread_pct": round(spread_pct, 2) if spread_pct is not None else None,
        })

    payload = {
        "symbol": symbol,
        "timestamp": ts,
        "mode": args.mode,
        "underlying_price": underlying,
        "total_contracts": len(result.contracts),
        "puts_count": len(puts),
        "puts_in_dte": puts_in_dte,
        "puts_with_required_fields": puts_with_required_fields,
        "missing_bid": missing_bid,
        "missing_ask": missing_ask,
        "missing_oi": missing_oi,
        "missing_delta": missing_delta,
        "expirations_selected": expirations_selected,
        "sample_puts_count": len(rows),
        "strikes_options_telemetry": getattr(result, "strikes_options_telemetry", None),
        "sample_puts": rows,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# ORATS harness: {symbol} ({ts})\n\n")
        f.write(f"Mode: {args.mode} | Underlying: {underlying} | PUTs: {len(puts)} | Sample: {len(rows)}\n\n")
        f.write("| optionSymbol | exp | strike | delta | bid | ask | oi | spread_pct |\n")
        f.write("|-------------|-----|--------|-------|-----|-----|-----|-------------|\n")
        for r in rows:
            f.write(f"| {r['option_symbol']} | {r['expiration']} | {r['strike']} | {r['delta']} | {r['bid']} | {r['ask']} | {r['open_interest']} | {r['spread_pct']} |\n")

    # Proof summary for Phase 1 validation
    proof_path = out_dir / f"{symbol}_proof_summary.md"
    sample_10 = rows[:10]
    with open(proof_path, "w", encoding="utf-8") as f:
        f.write(f"# {symbol} — ORATS delayed proof summary\n\n")
        f.write(f"**Expirations selected (in DTE window):** {', '.join(expirations_selected) or 'none'}\n\n")
        f.write(f"**Counts:**\n")
        f.write(f"- Total contracts fetched: {len(result.contracts)}\n")
        f.write(f"- PUTs in DTE: {puts_in_dte}\n")
        f.write(f"- PUTs with ALL required fields present: {puts_with_required_fields}\n")
        f.write(f"- Missing (bid/ask/oi/delta): {missing_bid}/{missing_ask}/{missing_oi}/{missing_delta}\n\n")
        f.write("**10 sample OTM PUTs (strike, |delta|, bid, ask, oi):**\n\n")
        f.write("| optionSymbol | strike | delta_abs | bid | ask | open_interest |\n")
        f.write("|--------------|--------|-----------|-----|-----|---------------|\n")
        for r in sample_10:
            d = r.get("delta")
            d_abs = abs(float(d)) if d is not None else ""
            f.write(f"| {r['option_symbol']} | {r['strike']} | {d_abs} | {r['bid']} | {r['ask']} | {r['open_interest']} |\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
