/**
 * UI API response types — exact backend contract (UI_CONTRACT_REPORT.md).
 * No field renaming. All nested objects typed.
 */

// =============================================================================
// ArtifactListResponse — GET /api/ui/decision/files?mode=LIVE|MOCK
// =============================================================================

export type DecisionMode = "LIVE" | "MOCK";

export interface ArtifactFile {
  name: string;
  mtime_iso: string;
  size_bytes: number;
}

export interface ArtifactListResponse {
  mode: DecisionMode;
  dir: string;
  files: ArtifactFile[];
}

// =============================================================================
// DecisionResponse (v2) — GET /api/ui/decision/latest returns { artifact, artifact_version }
// =============================================================================

/** V2 symbol row from artifact / universe. All render fields typed as string | number | null (not {}). */
export interface SymbolEvalSummary {
  symbol: string;
  verdict: string;
  final_verdict: string;
  score: number | null;
  band: "A" | "B" | "C" | "D";
  primary_reason: string | null;
  stage_status: string;
  stage1_status: string;
  stage2_status: string;
  provider_status: string | null;
  data_freshness: string | null;
  evaluated_at: string | null;
  strategy: string | null;
  price: number | null;
  expiration: string | null;
  has_candidates: boolean;
  candidate_count: number;
  band_reason: string | null;
  score_breakdown?: unknown;
  raw_score?: number | null;
  score_caps?: { regime_cap?: number | null; applied_caps?: Array<{ type: string; cap_value: number; before: number; after: number; reason: string }> } | null;
  rank_score?: number | null;
  capital_required?: number | null;
  premium_yield_pct?: number | null;
  market_cap?: number | null;
}

export interface DecisionArtifactV2Metadata {
  artifact_version: "v2";
  mode?: string;
  pipeline_timestamp: string;
  market_phase?: string;
  universe_size?: number;
  evaluated_count_stage1?: number;
  evaluated_count_stage2?: number;
  eligible_count?: number;
  warnings?: string[];
}

export interface DecisionArtifactV2 {
  artifact_version: "v2";
  metadata: DecisionArtifactV2Metadata;
  symbols: SymbolEvalSummary[];
  selected_candidates?: Array<{ symbol: string; strategy?: string; [key: string]: unknown }>;
}

/** GET /api/ui/decision/latest (v2): { artifact, artifact_version, evaluation_timestamp_utc, decision_store_mtime_utc } */
export interface DecisionResponse {
  artifact: DecisionArtifactV2;
  artifact_version?: "v2" | string;
  /** Phase 9: Canonical last evaluation time (pipeline_timestamp or file mtime). */
  evaluation_timestamp_utc?: string | null;
  decision_store_mtime_utc?: string | null;
}

// Legacy types (kept for reference; API is v2-only)
export interface DecisionCandidateContract {
  strategy: string;
  expiry: string;
  strike: number;
  delta: number;
  credit_estimate: number;
  max_loss: number;
  why_this_trade: string;
}

export interface DecisionCandidate {
  symbol: string;
  verdict: string;
  candidate: DecisionCandidateContract;
}

export interface DecisionSelectedSignal {
  symbol: string;
  candidate: DecisionCandidateContract;
  verdict: string;
}

export interface DecisionSnapshotStats {
  symbols_evaluated: number;
  total_candidates: number;
  selected_count: number;
}

export interface DecisionWhyNoTrade {
  summary: string;
}

export interface DecisionSnapshot {
  stats: DecisionSnapshotStats;
  candidates: DecisionCandidate[];
  selected_signals: DecisionSelectedSignal[];
  exclusions: unknown[];
  data_source: string;
  as_of: string;
  pipeline_timestamp: string;
  trade_proposal: unknown;
  why_no_trade: DecisionWhyNoTrade;
}

export interface ExecutionGateResult {
  allowed: boolean;
  reasons: string[];
}

export interface ExecutionPlan {
  allowed: boolean;
  blocked_reason: string;
  orders: unknown[];
}

export interface DryRunResult {
  allowed: boolean;
}

export interface DecisionMetadata {
  data_source: string;
  pipeline_timestamp: string;
}

// =============================================================================
// UniverseResponse — GET /api/ui/universe (v2: symbols are SymbolEvalSummary[])
// =============================================================================

/** @deprecated Use SymbolEvalSummary for v2. Kept for compatibility. */
export type UniverseSymbol = SymbolEvalSummary;

/** Phase 7.1: Merged universe row with explicit evaluation state. No blanks. */
export interface UniverseMergedRow {
  symbol: string;
  verdict: string;
  final_verdict: string;
  score: number | null;
  band: string | null;
  primary_reason: string | null;
  price: number | null;
  expiration: string | null;
  stage_status: string;
  provider_status: string | null;
  stage1_status: string;
  stage2_status: string;
  data_freshness: string | null;
  has_candidates: boolean;
  evaluated_at: string | null;
  strategy: string | null;
}

export interface UniverseResponse {
  source: string;
  updated_at: string;
  as_of: string;
  symbols: SymbolEvalSummary[];
  error?: string;
}

// =============================================================================
// SymbolDiagnosticsResponse — GET /api/ui/symbol-diagnostics?symbol=
// =============================================================================

export interface SymbolDiagnosticsStock {
  price: number | null;
  bid: number | null;
  ask: number | null;
  volume: number | null;
  avg_option_volume_20d: number | null;
  avg_stock_volume_20d: number | null;
  quote_as_of: string | null;
  stock_volume_today: number | null;
  field_sources: Record<string, string> | null;
  missing_reasons: string[] | null;
}

export interface SymbolDiagnosticsGate {
  name: string;
  status: string;
  pass: boolean;
  reason: string;
  code?: string;
}

export interface SymbolDiagnosticsBlocker {
  code: string;
  message: string;
  severity: string;
  impact: string;
}

export interface SymbolDiagnosticsResponse {
  symbol: string;
  primary_reason: string | null;
  verdict: string | null;
  in_universe: boolean;
  stock: SymbolDiagnosticsStock | null;
  gates: SymbolDiagnosticsGate[];
  blockers: SymbolDiagnosticsBlocker[];
  notes: string[];
}

// =============================================================================
// UiSystemHealthResponse — GET /api/ui/system-health
// =============================================================================

export interface UiSystemHealthApi {
  status: "OK" | "DOWN";
  latency_ms?: number;
}

export interface UiSystemHealthOrats {
  status: "OK" | "WARN" | "DOWN";
  last_success_at: string | null;
  avg_latency_seconds: number | null;
  last_error_reason?: string | null;
  /** Phase 9 */
  last_success_at_utc?: string | null;
  age_minutes?: number | null;
  staleness_threshold_minutes?: number | null;
}

export interface UiSystemHealthMarket {
  phase: string;
  is_open: boolean;
  timestamp: string | null;
}

export interface UiSystemHealthScheduler {
  interval_minutes?: number | null;
  nightly_next_at?: string | null;
  eod_next_at?: string | null;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_result?: string | null;
}

/** PR2: EOD freeze snapshot scheduler status. */
export interface UiSystemHealthEodFreeze {
  enabled?: boolean;
  scheduled_time_et?: string | null;
  last_run_at_utc?: string | null;
  last_run_at_et?: string | null;
  last_result?: string | null;
  last_snapshot_dir?: string | null;
}

export interface UiSystemHealthDecisionStore {
  status: "OK" | "CRITICAL";
  reason?: string | null;
  canonical_path?: string | null;
  /** Phase 9 */
  evaluation_timestamp_utc?: string | null;
  decision_store_mtime_utc?: string | null;
}


export interface UiSystemHealthResponse {
  api: UiSystemHealthApi;
  decision_store?: UiSystemHealthDecisionStore;
  orats: UiSystemHealthOrats;
  market: UiSystemHealthMarket;
  scheduler: UiSystemHealthScheduler;
  eod_freeze?: UiSystemHealthEodFreeze;
}

// =============================================================================
// UiTrackedPosition — GET /api/ui/positions/tracked
// =============================================================================

export interface UiTrackedPosition {
  id?: string | null;
  symbol: string;
  qty?: number | null;
  contracts?: number | null;
  avg_price?: number | null;
  collateral?: number | null;
  notional?: number | null;
  updated_at?: string | null;
  status?: string | null;
  is_test?: boolean;
}

export interface UiTrackedPositionsResponse {
  positions: UiTrackedPosition[];
  capital_deployed?: number;
  open_positions_count?: number;
}

// =============================================================================
// Portfolio — GET /api/ui/portfolio (lifecycle-enriched positions)
// =============================================================================

export interface PortfolioPosition {
  position_id: string;
  id?: string | null;
  symbol: string;
  strategy: string;
  is_test?: boolean;
  entry_credit?: number | null;
  quantity?: number | null;
  contracts?: number | null;
  strike?: number | null;
  expiry?: string | null;
  entry_date?: string | null;
  status?: string | null;
  stop_price?: number | null;
  t1?: number | null;
  t2?: number | null;
  t3?: number | null;
  mark?: number | null;
  premium_captured_pct?: number | null;
  dte?: number | null;
  alert_flags?: string[];
  unrealized_pnl?: number | null;
}

export interface PortfolioResponse {
  positions: PortfolioPosition[];
  capital_deployed?: number;
  open_positions_count?: number;
}

// =============================================================================
// Alerts — GET /api/ui/alerts
// =============================================================================

export interface UiAlert {
  position_id: string;
  symbol: string;
  type: string;
  message: string;
}

export interface UiAlertsResponse {
  alerts: UiAlert[];
}

// =============================================================================
// Symbol diagnostics extended (stage breakdown, liquidity, execution confidence)
// =============================================================================

export interface SymbolEligibilityDetail {
  status: string;
  required_data_missing: string[];
  required_data_stale: string[];
  optional_missing?: string[];
  reasons: string[];
}

export interface SymbolLiquidityDetail {
  stock_liquidity_ok: boolean | null;
  option_liquidity_ok: boolean | null;
  reason: string | null;
  /** True if Stage2 ran and liquidity was evaluated; false when Stage2 did not run (show NOT_EVALUATED). */
  liquidity_evaluated?: boolean;
}

/** Eligibility trace computed fields (RSI, ATR, S/R). */
export interface SymbolDiagnosticsComputed {
  rsi?: number | null;
  atr?: number | null;
  atr_pct?: number | null;
  support_level?: number | null;
  resistance_level?: number | null;
}

/** Exit plan structure (T1, T2, T3, stop hint). */
export interface SymbolDiagnosticsExitPlan {
  t1?: number | null;
  t2?: number | null;
  t3?: number | null;
  stop?: number | null;
}

/** Candidate trade (strike, expiry, delta, credit_estimate, max_loss). */
export interface SymbolDiagnosticsCandidate {
  strategy?: string;
  strike?: number | null;
  expiry?: string | null;
  delta?: number | null;
  credit_estimate?: number | null;
  max_loss?: number | null;
  why_this_trade?: string | null;
}

/** Score breakdown (raw_score, final_score, composite_score, caps). */
export interface SymbolDiagnosticsScoreBreakdown {
  data_quality_score?: number;
  regime_score?: number;
  options_liquidity_score?: number;
  strategy_fit_score?: number;
  capital_efficiency_score?: number;
  composite_score?: number;
  raw_score?: number | null;
  final_score?: number | null;
  score_caps?: { regime_cap?: number | null; applied_caps?: Array<{ type: string; cap_value: number; before: number; after: number; reason: string }> } | null;
  csp_notional?: number | null;
  notional_pct?: number | null;
}

/** Rank reasons (reasons[], penalty). */
export interface SymbolDiagnosticsRankReasons {
  reasons?: string[];
  penalty?: string | null;
}

/** Phase 7.3: Structured explanation (symbol-level). */
export interface SymbolDiagnosticsExplanation {
  stock_regime_reason?: string | null;
  support_condition?: string | null;
  liquidity_condition?: string | null;
  iv_condition?: string | null;
}

export interface SymbolDiagnosticsResponseExtended extends SymbolDiagnosticsResponse {
  symbol_eligibility?: SymbolEligibilityDetail;
  liquidity?: SymbolLiquidityDetail;
  /** Phase 7.3: Structured explanation. */
  explanation?: SymbolDiagnosticsExplanation | null;
  /** Eligibility trace computed: RSI, ATR, support/resistance levels. */
  computed?: SymbolDiagnosticsComputed;
  /** Composite score (0-100). */
  composite_score?: number | null;
  /** Confidence band (A | B | C). */
  confidence_band?: string | null;
  /** Suggested capital % per position. */
  suggested_capital_pct?: number | null;
  /** Reason for band assignment. */
  band_reason?: string | null;
  /** Full candidate contract list. */
  candidates?: SymbolDiagnosticsCandidate[];
  /** Exit plan (t1, t2, t3, stop). */
  exit_plan?: SymbolDiagnosticsExitPlan;
  /** Score breakdown. */
  score_breakdown?: SymbolDiagnosticsScoreBreakdown | null;
  /** Rank reasons. */
  rank_reasons?: SymbolDiagnosticsRankReasons | null;
  /** Raw score (uncapped composite 0–100). */
  raw_score?: number | null;
  /** Score caps (regime_cap, applied_caps). */
  score_caps?: { regime_cap?: number | null; applied_caps?: Array<{ type: string; cap_value: number; before: number; after: number; reason: string }> } | null;
  /** Regime (UP | DOWN | SIDEWAYS from eligibility). */
  regime?: string | null;
  /** Provider status: OK | NOT_FOUND | NO_CHAIN | ERROR. */
  provider_status?: string | null;
  /** Human-readable message when provider_status is not OK. */
  provider_message?: string | null;
}
