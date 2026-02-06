/**
 * Phase 10: Symbol diagnostics API response shape.
 * Full explainability: every decision must be explainable.
 */

// Stock snapshot
export interface StockSnapshot {
  price: number | null;
  bid: number | null;
  ask: number | null;
  volume: number | null;
  avg_volume: number | null;
  trend: "UP" | "DOWN" | "NEUTRAL";
}

// Phase 8: Strategy rationale (from evaluation run)
export interface StrategyRationale {
  summary: string;
  bullets: string[];
  failed_checks: string[];
  data_warnings: string[];
}

// Phase 3: Score breakdown (components 0–100 + composite)
export interface ScoreBreakdown {
  data_quality_score: number;
  regime_score: number;
  options_liquidity_score: number;
  strategy_fit_score: number;
  capital_efficiency_score: number;
  composite_score: number;
  csp_notional?: number | null;
  notional_pct?: number | null;
  capital_penalties?: string[];
  top_penalty?: string | null;
}

// Phase 10: Capital hint from confidence band; Phase 3: band_reason explains why
export interface CapitalHint {
  band: "A" | "B" | "C";
  suggested_capital_pct: number;
  band_reason?: string | null;
}

// Eligibility verdict
export interface Eligibility {
  verdict: "ELIGIBLE" | "HOLD" | "BLOCKED" | "UNKNOWN";
  primary_reason: string;
  confidence_score: number | null;
  score?: number;
  /** Phase 8: Human-readable explanation from evaluation run */
  rationale?: StrategyRationale | null;
  /** Phase 9: Position already open for this symbol */
  position_open?: boolean;
  position_reason?: string | null;
  /** Phase 10: Confidence band and suggested capital % */
  capital_hint?: CapitalHint | null;
  /** Phase 3: Score breakdown (components + composite) and rank reasons */
  score_breakdown?: ScoreBreakdown | null;
  rank_reasons?: { reasons: string[]; penalty: string | null } | null;
  csp_notional?: number | null;
  notional_pct?: number | null;
  band_reason?: string | null;
  /** Verdict reason code for consistent classification */
  verdict_reason_code?: string | null;
  /** DATA_INCOMPLETE type: FATAL, INTRADAY, or null */
  data_incomplete_type?: string | null;
  /** Whether this came from persisted evaluation run */
  from_persisted_run?: boolean;
  /** Run ID if from persisted run */
  run_id?: string | null;
  /** When this symbol was evaluated */
  evaluated_at?: string | null;
}

// Regime assessment
export interface RegimeAssessment {
  market_regime: string | null;
  allowed: boolean;
  reason: string;
}

// Risk assessment
export interface RiskAssessment {
  posture: string | null;
  allowed: boolean;
  reason: string;
}

// Liquidity assessment
export interface LiquidityAssessment {
  stock_liquidity_ok: boolean;
  option_liquidity_ok: boolean;
  reason: string;
}

// Greeks summary
export interface GreeksSummary {
  iv_rank: number | null;
  iv_percentile: number | null;
  delta_target_range: string | null;
  theta_bias: string | null;
}

// Candidate trade
export interface CandidateTrade {
  strategy: "CSP" | "CC" | "HOLD" | string;
  description?: string;
  expiry: string | null;
  strike: number | null;
  delta: number | null;
  credit_estimate: number | null;
  max_loss: number | null;
  why_this_trade: string | null;
}

// Alias for clarity in other files
export type SymbolDiagnosticsCandidateTrade = CandidateTrade;

export interface SymbolDiagnosticsMarket {
  regime: string | null;
  risk_posture: string | null;
}

export interface SymbolDiagnosticsGate {
  name: string;
  pass: boolean;
  status?: "PASS" | "FAIL";
  detail?: string;
  reason?: string;
  code?: string | null;
}

export interface SymbolDiagnosticsBlocker {
  code: string;
  message: string;
  severity?: string;
  impact?: string;
}

export interface SymbolDiagnosticsEarnings {
  next_date: string | null;
  days_to_earnings: number | null;
  blocked: boolean;
  reason?: string;
}

export interface SymbolDiagnosticsOptions {
  has_options: boolean;
  chain_ok: boolean;
  expirations_count?: number | null;
  contracts_count?: number | null;
  underlying_price?: number | null;
}

// Selected contract from 2-stage evaluation
export interface SelectedContractInfo {
  contract: {
    symbol: string;
    expiration: string;
    strike: number;
    option_type: "PUT" | "CALL";
    bid: number | null;
    ask: number | null;
    mid: number | null;
    open_interest: number | null;
    volume: number | null;
    delta: number | null;
    gamma: number | null;
    theta: number | null;
    vega: number | null;
    iv: number | null;
    dte: number;
    spread: number | null;
    spread_pct: number | null;
    liquidity_grade: "A" | "B" | "C" | "D" | "F";
  };
  selection_reason: string;
  meets_all_criteria: boolean;
  criteria_results?: Record<string, boolean>;
}

export interface SymbolDiagnosticsView {
  symbol: string;
  in_universe: boolean;
  universe_reason?: string | null;
  /** OUT_OF_SCOPE when symbol not in universe */
  status?: string | null;
  reason?: string | null;
  snapshot_time: string | null;
  fetched_at?: string | null;
  /** Seconds from ORATS fetch (data freshness). */
  data_latency_seconds?: number | null;
  
  // Full explainability fields
  stock?: StockSnapshot;
  eligibility?: Eligibility;
  regime?: RegimeAssessment;
  risk?: RiskAssessment;
  liquidity?: LiquidityAssessment;
  greeks_summary?: GreeksSummary;
  candidate_trades?: CandidateTrade[];
  
  // Legacy fields
  market: SymbolDiagnosticsMarket;
  gates: SymbolDiagnosticsGate[];
  blockers: SymbolDiagnosticsBlocker[];
  earnings: SymbolDiagnosticsEarnings;
  options: SymbolDiagnosticsOptions;
  recommendation: "ELIGIBLE" | "NOT_ELIGIBLE" | "UNKNOWN";
  notes?: string[];
  
  // 2-Stage pipeline fields
  stage_reached?: "NOT_STARTED" | "STAGE1_ONLY" | "STAGE2_CHAIN";
  selected_contract?: SelectedContractInfo;
  selected_expiration?: string;
}
