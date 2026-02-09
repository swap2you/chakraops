/**
 * Phase 2A: Ranked opportunity types for dashboard decision intelligence.
 * Matches backend app.core.ranking.service output.
 */

import type { ScoreBreakdown } from "./symbolDiagnostics";

export interface RankedOpportunity {
  rank: number;
  symbol: string;
  strategy: "CSP" | "CC" | "STOCK";
  band: "A" | "B" | "C";
  score: number;
  capital_required: number | null;
  capital_pct: number | null;
  rank_reason: string;
  primary_reason: string;
  price: number | null;
  strike: number | null;
  expiry: string | null;
  credit_estimate: number | null;
  delta: number | null;
  liquidity_ok: boolean;
  position_open: boolean;
  data_completeness: number | null;
  stage_reached: string | null;
  score_breakdown: ScoreBreakdown | null;
  rank_reasons: { reasons: string[]; penalty: string | null } | null;
  /** Phase 3: Risk status (OK/WARN/BLOCKED) */
  risk_status?: "OK" | "WARN" | "BLOCKED";
  /** Phase 3: Human-readable risk block reasons */
  risk_reasons?: string[];
  /** Phase 6: Required fields missing (data BLOCK) */
  required_data_missing?: string[];
  /** Phase 6: Optional fields missing */
  optional_data_missing?: string[];
  /** Phase 6: Required fields stale */
  required_data_stale?: string[];
  /** Phase 6: Provider timestamps */
  data_as_of_orats?: string | null;
  data_as_of_price?: string | null;
}

export interface OpportunitiesResponse {
  opportunities: RankedOpportunity[];
  count: number;
  evaluation_id: string | null;
  evaluated_at: string | null;
  account_equity: number | null;
  total_eligible: number;
  error?: string;
}
