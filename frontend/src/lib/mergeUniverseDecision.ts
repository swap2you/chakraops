/**
 * Merge Universe + Decision data for non-blank UI.
 * Uses /api/ui/universe as base, overlays verdict/score/band/expiration from decision.
 */

import type { UniverseSymbol } from "@/api/types";
import type { DecisionResponse, DecisionCandidate } from "@/api/types";

export function mergeUniverseWithDecision(
  universeSymbols: UniverseSymbol[],
  decision: DecisionResponse | undefined
): UniverseSymbol[] {
  if (!decision?.decision_snapshot?.candidates?.length) {
    return universeSymbols;
  }
  const bySymbol = new Map<string, DecisionCandidate>();
  for (const c of decision.decision_snapshot.candidates) {
    const sym = (c.symbol || "").toUpperCase();
    if (sym) bySymbol.set(sym, c);
  }
  return universeSymbols.map((s) => {
    const sym = (s.symbol || "").toUpperCase();
    const cand = bySymbol.get(sym);
    if (!cand) return s;
    const contract = cand.candidate;
    const merged: UniverseSymbol = { ...s };
    if (cand.verdict != null && cand.verdict !== "") merged.verdict = cand.verdict;
    if (cand.verdict != null && cand.verdict !== "") merged.final_verdict = cand.verdict;
    if (contract?.expiry != null) merged.expiration = String(contract.expiry).slice(0, 10);
    if ((s as { score?: number }).score == null && (cand as { score?: number }).score != null) {
      merged.score = (cand as { score?: number }).score;
    }
    if ((s as { band?: string }).band == null && (cand as { band?: string }).band != null) {
      merged.band = (cand as { band?: string }).band;
    }
    if ((s as { primary_reason?: string }).primary_reason == null && (cand as { primary_reason?: string }).primary_reason != null) {
      merged.primary_reason = (cand as { primary_reason?: string }).primary_reason;
    }
    if ((s as { price?: number }).price == null && contract != null && (contract as { price?: number }).price != null) {
      merged.price = (contract as { price?: number }).price;
    }
    return merged;
  });
}

/** Build merged list when universe is empty: use decision.candidates as base. */
export function buildSymbolsFromDecision(
  decision: DecisionResponse | undefined
): UniverseSymbol[] {
  if (!decision?.decision_snapshot?.candidates?.length) return [];
  const seen = new Set<string>();
  const out: UniverseSymbol[] = [];
  for (const c of decision.decision_snapshot.candidates) {
    const sym = (c.symbol || "").toUpperCase();
    if (!sym || seen.has(sym)) continue;
    seen.add(sym);
    const contract = c.candidate;
    out.push({
      symbol: c.symbol,
      verdict: c.verdict,
      final_verdict: c.verdict,
      score: (c as { score?: number }).score,
      band: (c as { band?: string }).band,
      primary_reason: (c as { primary_reason?: string }).primary_reason,
      expiration: contract?.expiry != null ? String(contract.expiry).slice(0, 10) : undefined,
      price: (contract as { price?: number })?.price,
    });
  }
  return out;
}
