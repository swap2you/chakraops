/**
 * Phase 7.1: Strict merge of Universe + Decision. Data integrity only.
 * - Universe is the source of truth for symbol set.
 * - Decision overlays evaluation state by symbol; never assume decision covers full universe.
 * - Symbols not in decision get explicit fallback state: NOT_EVALUATED, NOT_RUN, etc.
 */

import type { UniverseSymbol } from "@/api/types";
import type { UniverseMergedRow } from "@/api/types";
import type { DecisionResponse, DecisionCandidate } from "@/api/types";

const FALLBACK_VERDICT = "NOT_EVALUATED";
const FALLBACK_STAGE = "NOT_RUN";

function fallbackRow(symbol: string, base?: UniverseSymbol): UniverseMergedRow {
  return {
    symbol: base?.symbol ?? symbol,
    verdict: FALLBACK_VERDICT,
    final_verdict: FALLBACK_VERDICT,
    score: null,
    band: null,
    primary_reason: null,
    price: base?.price != null ? base.price : null,
    expiration: base?.expiration ?? null,
    stage_status: FALLBACK_STAGE,
    provider_status: null,
    stage1_status: FALLBACK_STAGE,
    stage2_status: FALLBACK_STAGE,
    data_freshness: null,
    has_candidates: false,
    evaluated_at: null,
    strategy: null,
  };
}

function toMergedRow(
  symbol: string,
  base: UniverseSymbol | undefined,
  cand: DecisionCandidate | undefined,
  evaluatedAt: string | null
): UniverseMergedRow {
  if (!cand) {
    return fallbackRow(symbol, base);
  }
  const contract = cand.candidate;
  const strategy = contract?.strategy ?? null;
  const hasCandidates = !!(contract && (contract.strategy ?? contract.expiry));
  return {
    symbol: base?.symbol ?? cand.symbol ?? symbol,
    verdict: cand.verdict ?? FALLBACK_VERDICT,
    final_verdict: cand.verdict ?? FALLBACK_VERDICT,
    score: (cand as { score?: number }).score ?? (base as { score?: number })?.score ?? null,
    band: (cand as { band?: string }).band ?? (base as { band?: string })?.band ?? null,
    primary_reason: (cand as { primary_reason?: string }).primary_reason ?? base?.primary_reason ?? null,
    price: (contract as { price?: number })?.price ?? base?.price ?? null,
    expiration: contract?.expiry != null ? String(contract.expiry).slice(0, 10) : (base?.expiration ?? null),
    stage_status: "RUN",
    provider_status: "OK",
    stage1_status: "PASS",
    stage2_status: hasCandidates ? "PASS" : "RUN",
    data_freshness: evaluatedAt,
    has_candidates: hasCandidates,
    evaluated_at: evaluatedAt,
    strategy: strategy,
  };
}

/**
 * Merge universe symbols with decision. Universe is base; decision overlays by symbol.
 * Symbols not in decision get fallback state (NOT_EVALUATED, NOT_RUN, nulls).
 */
export function mergeUniverseWithDecision(
  universeSymbols: UniverseSymbol[],
  decision: DecisionResponse | undefined
): UniverseMergedRow[] {
  const bySymbol = new Map<string, DecisionCandidate>();
  if (decision?.decision_snapshot?.candidates?.length) {
    for (const c of decision.decision_snapshot.candidates) {
      const sym = (c.symbol || "").toUpperCase();
      if (sym) bySymbol.set(sym, c);
    }
  }
  const selectedBySymbol = new Map<string, DecisionCandidate>();
  if (decision?.decision_snapshot?.selected_signals?.length) {
    for (const s of decision.decision_snapshot.selected_signals) {
      const sym = (s.symbol || "").toUpperCase();
      if (sym) selectedBySymbol.set(sym, { symbol: s.symbol, verdict: s.verdict, candidate: s.candidate });
    }
  }
  const evaluatedAt = decision?.metadata?.pipeline_timestamp ?? null;

  return universeSymbols.map((s) => {
    const sym = (s.symbol || "").toUpperCase();
    const cand = bySymbol.get(sym) ?? selectedBySymbol.get(sym);
    return toMergedRow(sym, s, cand, evaluatedAt);
  });
}

/**
 * When universe is empty, build rows from decision only. All such symbols are evaluated.
 */
export function buildSymbolsFromDecision(
  decision: DecisionResponse | undefined
): UniverseMergedRow[] {
  if (!decision?.decision_snapshot) return [];
  const evaluatedAt = decision.metadata?.pipeline_timestamp ?? null;
  const seen = new Set<string>();
  const rows: UniverseMergedRow[] = [];
  const add = (c: DecisionCandidate) => {
    const sym = (c.symbol || "").toUpperCase();
    if (!sym || seen.has(sym)) return;
    seen.add(sym);
    rows.push(toMergedRow(sym, undefined, c, evaluatedAt));
  };
  for (const c of decision.decision_snapshot.candidates ?? []) {
    add(c);
  }
  for (const s of decision.decision_snapshot.selected_signals ?? []) {
    add(s);
  }
  return rows;
}
