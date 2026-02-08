/**
 * Phase 2B: Symbol intelligence types — explain, candidates, targets.
 */

export interface SymbolExplain {
  symbol: string;
  company: {
    symbol: string;
    name: string;
    description?: string | null;
    sector?: string | null;
    industry?: string | null;
  } | null;
  evaluation_id: string | null;
  evaluated_at: string | null;
  verdict: string;
  primary_reason: string;
  score: number;
  band: string;
  gates: Array<{ name: string; status: string; reason: string; metric?: string }>;
  primary_strategy: "CSP" | "CC" | "STOCK" | null;
  strategy_why_bullets: string[];
  capital_required: number | null;
  capital_pct: number | null;
  account_equity: number | null;
  score_breakdown: Record<string, number> | null;
  rank_reasons: { reasons: string[]; penalty: string | null } | null;
  data_coverage: { present: string[]; missing: string[] };
  error?: string;
}

export interface ContractCandidate {
  rank: number;
  label: string;
  expiration: string | null;
  strike: number | null;
  delta: number | null;
  iv: number | null;
  bid: number | null;
  ask: number | null;
  mid: number | null;
  premium_per_contract: number | null;
  collateral_per_contract: number | null;
  dte: number | null;
  liquidity_grade: string | null;
}

export interface SymbolCandidates {
  symbol: string;
  strategy: string | null;
  candidates: ContractCandidate[];
  recommended_contracts: number;
  capital_required: number | null;
  capital_pct: number | null;
  account_equity: number | null;
  evaluation_id: string | null;
  evaluated_at: string | null;
  error?: string;
}

export interface SymbolTargets {
  symbol: string;
  entry_low: number | null;
  entry_high: number | null;
  stop: number | null;
  target1: number | null;
  target2: number | null;
  notes: string;
}
