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
// DecisionResponse — GET /api/ui/decision/latest, GET /api/ui/decision/file/{filename}
// =============================================================================

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

export interface DecisionResponse {
  decision_snapshot: DecisionSnapshot;
  execution_gate_result: ExecutionGateResult;
  execution_gate: ExecutionGateResult;
  execution_plan: ExecutionPlan;
  dry_run_result: DryRunResult;
  metadata: DecisionMetadata;
}

// =============================================================================
// UniverseResponse — GET /api/ui/universe
// =============================================================================

export interface UniverseSymbol {
  symbol: string;
  price?: number;
  expiration?: string;
  final_verdict?: string;
  verdict?: string;
  score?: number;
  band?: string;
  primary_reason?: string;
  [key: string]: unknown;
}

export interface UniverseResponse {
  source: string;
  updated_at: string;
  as_of: string;
  symbols: UniverseSymbol[];
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
}

export interface UiSystemHealthResponse {
  api: UiSystemHealthApi;
  orats: UiSystemHealthOrats;
  market: UiSystemHealthMarket;
  scheduler: UiSystemHealthScheduler;
}

// =============================================================================
// UiTrackedPosition — GET /api/ui/positions/tracked
// =============================================================================

export interface UiTrackedPosition {
  symbol: string;
  qty?: number | null;
  contracts?: number | null;
  avg_price?: number | null;
  notional?: number | null;
  updated_at?: string | null;
  status?: string | null;
}

export interface UiTrackedPositionsResponse {
  positions: UiTrackedPosition[];
}

// =============================================================================
// Symbol diagnostics extended (stage breakdown, liquidity, execution confidence)
// =============================================================================

export interface SymbolEligibilityDetail {
  status: string;
  required_data_missing: string[];
  required_data_stale: string[];
  reasons: string[];
}

export interface SymbolLiquidityDetail {
  stock_liquidity_ok: boolean | null;
  option_liquidity_ok: boolean | null;
  reason: string | null;
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

/** Score breakdown (composite_score, component scores). */
export interface SymbolDiagnosticsScoreBreakdown {
  data_quality_score?: number;
  regime_score?: number;
  options_liquidity_score?: number;
  strategy_fit_score?: number;
  capital_efficiency_score?: number;
  composite_score?: number;
  csp_notional?: number | null;
  notional_pct?: number | null;
}

/** Rank reasons (reasons[], penalty). */
export interface SymbolDiagnosticsRankReasons {
  reasons?: string[];
  penalty?: string | null;
}

export interface SymbolDiagnosticsResponseExtended extends SymbolDiagnosticsResponse {
  symbol_eligibility?: SymbolEligibilityDetail;
  liquidity?: SymbolLiquidityDetail;
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
  /** Regime (UP | DOWN | SIDEWAYS from eligibility). */
  regime?: string | null;
  /** Provider status: OK | NOT_FOUND | NO_CHAIN | ERROR. */
  provider_status?: string | null;
  /** Human-readable message when provider_status is not OK. */
  provider_message?: string | null;
}
