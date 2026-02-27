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
  /** Phase 11.3: From selected candidate (strike-expiry-PUT|CALL) */
  selected_contract_key?: string | null;
  /** Phase 11.3: OCC option symbol when ELIGIBLE */
  option_symbol?: string | null;
  /** Phase 11.3: Strike from selected candidate when ELIGIBLE */
  strike?: number | null;
  score_breakdown?: unknown;
  raw_score?: number | null;
  final_score?: number | null;
  pre_cap_score?: number | null;
  score_caps?: { regime_cap?: number | null; applied_caps?: Array<{ type: string; cap_value: number; before: number; after: number; reason?: string; reason_code?: string }> } | null;
  rank_score?: number | null;
  capital_required?: number | null;
  premium_yield_pct?: number | null;
  market_cap?: number | null;
  /** Plain-English reasons with key numbers (additive; keep primary_reason for debug). */
  reasons_explained?: ReasonExplained[];
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

/** GET /api/ui/decision/latest (v2): { artifact, artifact_version, evaluation_timestamp_utc, run_id } */
export interface DecisionResponse {
  artifact: DecisionArtifactV2;
  artifact_version?: "v2" | string;
  /** Phase 9: Canonical last evaluation time (pipeline_timestamp or file mtime). */
  evaluation_timestamp_utc?: string | null;
  decision_store_mtime_utc?: string | null;
  /** Phase 11.1: Stable run id (uuid) for traceability */
  run_id?: string | null;
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

/** Phase 21.3: GET /api/ui/universe/symbols — effective list + overlay counts */
export interface UniverseSymbolsResponse {
  base_count: number;
  overlay_added_count: number;
  overlay_removed_count: number;
  symbols: string[];
}

// =============================================================================
// SymbolDiagnosticsResponse — GET /api/ui/symbol-diagnostics?symbol=
// =============================================================================

export interface SymbolDiagnosticsStock {
  price: number | null;
  /** Alias for price when present from API (spot at evaluation). */
  spot?: number | null;
  /** Alias for price when present from API. */
  underlying_price?: number | null;
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
  /** R22.2: OK / DELAYED / WARN / ERROR; DELAYED is not WARN */
  orats_freshness_state?: "OK" | "DELAYED" | "WARN" | "ERROR" | string | null;
  orats_freshness_state_label?: string | null;
  /** R22.2: Effective data timestamp (ISO); which threshold triggered state */
  orats_as_of?: string | null;
  orats_threshold_triggered?: string | null;
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
  /** Phase 21.5: Why last run was skipped (market_closed, evaluation_running, no_symbols, etc.) */
  last_skip_reason?: string | null;
  /** R21.5.1: Scheduler heartbeat */
  last_duration_ms?: number | null;
  last_run_ok?: boolean | null;
  last_run_error?: string | null;
  run_count_today?: number | null;
}

/** Per-channel Slack status (R21.5.1) */
export interface UiSystemHealthSlackChannel {
  last_send_at?: string | null;
  last_send_ok?: boolean | null;
  last_error?: string | null;
  last_payload_type?: string | null;
}

/** Phase 21.5 / R21.5.1: Slack sender status (flat + channels map) */
export interface UiSystemHealthSlack {
  last_send_at?: string | null;
  last_send_ok?: boolean | null;
  last_error?: string | null;
  last_channel?: string | null;
  last_payload_type?: string | null;
  /** R21.5.1: Per-channel status */
  channels?: Record<string, UiSystemHealthSlackChannel> | null;
  last_any_send_at?: string | null;
  last_any_send_ok?: boolean | null;
  last_any_send_error?: string | null;
}

/** PR2: EOD freeze snapshot scheduler status. Phase 11.3: last_error, next_scheduled_et. */
export interface UiSystemHealthEodFreeze {
  enabled?: boolean;
  scheduled_time_et?: string | null;
  last_run_at_utc?: string | null;
  last_run_at_et?: string | null;
  last_result?: string | null;
  last_snapshot_dir?: string | null;
  /** Phase 11.3: Error message when last_result=FAIL */
  last_error?: string | null;
  /** Phase 11.3: Next scheduled run (ET) */
  next_scheduled_et?: string | null;
}

export interface UiSystemHealthDecisionStore {
  status: "OK" | "CRITICAL";
  reason?: string | null;
  canonical_path?: string | null;
  /** Phase 9 */
  evaluation_timestamp_utc?: string | null;
  decision_store_mtime_utc?: string | null;
}

/** Phase 16.0: Mark refresh state from out/mark_refresh_state.json */
export interface UiSystemHealthMarkRefresh {
  last_run_at_utc?: string | null;
  last_result?: "PASS" | "WARN" | "FAIL" | null;
  updated_count?: number | null;
  skipped_count?: number | null;
  error_count?: number | null;
  errors_sample?: string[];
}

export interface UiSystemHealthResponse {
  api: UiSystemHealthApi;
  decision_store?: UiSystemHealthDecisionStore;
  orats: UiSystemHealthOrats;
  market: UiSystemHealthMarket;
  scheduler: UiSystemHealthScheduler;
  /** Phase 21.5 */
  slack?: UiSystemHealthSlack;
  eod_freeze?: UiSystemHealthEodFreeze;
  /** Phase 16.0 */
  mark_refresh?: UiSystemHealthMarkRefresh;
  /** R23.4.2/R23.4.3 — Copilot status; no secrets. key_source: which env var (or NONE). */
  copilot?: {
    enabled?: boolean;
    key_present?: boolean;
    key_format_ok?: boolean;
    key_source?: "COPILOT_OPENAI_API_KEY" | "OPENAI_API_KEY" | "NONE";
    model?: string;
    last_error_code?: string | null;
  };
  /** R24.3.1 — Portfolio risk notifier; safe status/label only (OK, Degraded, Advisory). */
  portfolio_risk_notifier?: { status?: string; label?: string };
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

/** Phase 11.1: decision_ref links position to evaluation run */
export interface DecisionRef {
  run_id?: string | null;
  evaluation_timestamp_utc?: string | null;
  artifact_source?: string | null;
  selected_contract_key?: string | null;
}

export interface PortfolioPosition {
  position_id: string;
  id?: string | null;
  symbol: string;
  strategy: string;
  is_test?: boolean;
  entry_credit?: number | null;
  decision_ref?: DecisionRef | null;
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
  /** Phase 12.0: Realized PnL when CLOSED */
  realized_pnl?: number | null;
}

export interface PortfolioResponse {
  positions: PortfolioPosition[];
  capital_deployed?: number;
  open_positions_count?: number;
  /** R23.0: Share positions (qty, avg_cost, last_price, market_value, unrealized_pnl when price available). */
  shares_positions?: SharePositionSummary[];
}

/** Phase 12.0: GET /api/ui/portfolio/metrics */
export interface PortfolioMetricsResponse {
  open_positions_count: number;
  capital_deployed: number;
  realized_pnl_total: number;
  win_rate: number | null;
  avg_pnl: number | null;
  avg_credit: number | null;
  avg_dte_at_entry: number | null;
}

// =============================================================================
// Phase 21.1: Account (SQLite) — GET /api/ui/account/summary, holdings, balances
// =============================================================================

export interface AccountSummary {
  account_id: string;
  name: string;
  broker: string | null;
  base_currency: string;
  cash: number;
  buying_power: number;
  holdings_count: number;
  profile_updated_at?: string | null;
  balances_updated_at?: string | null;
}

export interface AccountHolding {
  symbol: string;
  shares: number;
  avg_cost: number | null;
  source?: string | null;
  updated_at: string;
}

export interface AccountHoldingsResponse {
  holdings: AccountHolding[];
}

/** R23.0: Share position (one row per account+symbol). */
export interface SharePosition {
  id: string;
  account_id: string;
  symbol: string;
  quantity: number;
  avg_cost: number | null;
  opened_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  /** R25.2: Optional target/stop for shares exit lifecycle. */
  target_price?: number | null;
  stop_price?: number | null;
}

/** R23.0: Share position with optional MTM (from portfolio/symbol-diagnostics). */
export interface SharePositionSummary {
  symbol: string;
  quantity: number;
  avg_cost?: number | null;
  last_price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  updated_at?: string | null;
}

export interface SharesPositionsListResponse {
  account_id: string;
  positions: SharePosition[];
}

/** R23.5.0: Closed share position (from close endpoint or list closed). */
export interface ClosedSharePosition {
  id: string;
  account_id: string;
  symbol: string;
  quantity: number;
  avg_cost: number | null;
  opened_at: string | null;
  closed_at: string;
  exit_price: number;
  realized_pnl: number | null;
  close_notes: string | null;
}

export interface ClosedSharePositionsListResponse {
  account_id: string;
  positions: ClosedSharePosition[];
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

/** R21.4: Request-time computed values for Technical details panel (not persisted). */
export interface SymbolDiagnosticsComputedValues {
  rsi?: number | null;
  rsi_range?: [number, number];
  atr?: number | null;
  atr_pct?: number | null;
  support_level?: number | null;
  resistance_level?: number | null;
  regime?: string | null;
  delta_band?: [number, number];
  rejected_count?: number;
}

/** Exit plan structure (T1, T2, T3, stop hint). */
export interface SymbolDiagnosticsExitPlan {
  t1?: number | null;
  t2?: number | null;
  t3?: number | null;
  stop?: number | null;
  /** NOT_AVAILABLE when missing inputs; AVAILABLE when computed. */
  status?: string | null;
  /** Plain-English reason when status is NOT_AVAILABLE. */
  reason?: string | null;
  /** R23.4.5: SR_LEVEL when targets from S/R; ATR_FALLBACK when from ATR. */
  target_basis?: string | null;
  /** R23.4.5: daily | weekly | monthly when target_basis is SR_LEVEL. */
  level_source_timeframe?: string | null;
  /** R23.4.5: Distance from spot to T1 as fraction (e.g. 0.01 = 1%). */
  distance_to_t1_pct?: number | null;
}

/** One explained reason (code → plain-English with metrics). */
export interface ReasonExplained {
  code: string;
  severity?: string;
  title?: string;
  message: string;
  metrics?: Record<string, unknown>;
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
  /** Phase 11.3: Exact contract key from decision (strike-expiry-PUT|CALL) */
  contract_key?: string | null;
  /** Phase 11.3: OCC option symbol when available */
  option_symbol?: string | null;
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
  score_caps?: { regime_cap?: number | null; applied_caps?: Array<{ type: string; cap_value: number; before: number; after: number; reason?: string; reason_code?: string }> } | null;
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
  /** R21.4: Request-time technicals + thresholds (rsi_range, delta_band, rejected_count). Not persisted. */
  computed_values?: SymbolDiagnosticsComputedValues;
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
  /** Raw score (composite before cap). */
  raw_score?: number | null;
  /** Final score (after caps); band derived from this. Phase 10.1 */
  final_score?: number | null;
  /** Pre-cap score (same as raw_score). Phase 10.1 */
  pre_cap_score?: number | null;
  /** Score caps (regime_cap, applied_caps). */
  score_caps?: { regime_cap?: number | null; applied_caps?: Array<{ type: string; cap_value: number; before: number; after: number; reason?: string; reason_code?: string }> } | null;
  /** Regime (UP | DOWN | SIDEWAYS from eligibility). */
  regime?: string | null;
  /** Provider status: OK | NOT_FOUND | NO_CHAIN | ERROR. */
  provider_status?: string | null;
  /** Human-readable message when provider_status is not OK. */
  provider_message?: string | null;
  /** Phase 11.2: True when run_id matched history; false when fallback to latest. */
  exact_run?: boolean;
  /** Phase 11.2: Run ID when fetched with run_id param. */
  run_id?: string | null;
  /** Plain-English reasons with key numbers (top 3+ show more; raw codes in debug). */
  reasons_explained?: ReasonExplained[];
  /** R22.7: Multi-timeframe levels from resampled OHLC (request-time only; not persisted). */
  mtf_levels?: {
    monthly?: { support?: number | null; resistance?: number | null; as_of?: string; method?: string; bar_count?: number | null; status_code?: string } | null;
    weekly?: { support?: number | null; resistance?: number | null; as_of?: string; method?: string; bar_count?: number | null; status_code?: string } | null;
    daily?: { support?: number | null; resistance?: number | null; as_of?: string; method?: string; bar_count?: number | null; status_code?: string } | null;
    "4h"?: { support?: number | null; resistance?: number | null; as_of?: string; method?: string; bar_count?: number | null; status_code?: string } | null;
  } | null;
  /** R22.4: Methodology (candles_source, window, clustering_tolerance_pct, active_criteria). */
  methodology?: { candles_source?: string; window?: string; clustering_tolerance_pct?: number; active_criteria?: string } | null;
  /** R22.4: Targets t1/t2/t3. R23.4.5: target_basis, level_source_timeframe, distance_to_t1_pct, targets_already_exceeded. */
  targets?: {
    t1?: number | null;
    t2?: number | null;
    t3?: number | null;
    target_basis?: string | null;
    level_source_timeframe?: string | null;
    distance_to_t1_pct?: number | null;
    targets_already_exceeded?: boolean | null;
  } | null;
  /** R22.4: Invalidation level. */
  invalidation?: number | null;
  /** R22.4: Hold-time estimate (sessions + basis_key for display mapping). */
  /** R23.4.7: hold_time_basis (e.g. 'ATR-based'), hold_time_atr, hold_time_distance_to_t1, hold_time_sessions; nulls when unavailable */
  hold_time_estimate?: {
    sessions?: number;
    basis_key?: string;
    hold_time_basis?: string | null;
    hold_time_atr?: number | null;
    hold_time_distance_to_t1?: number | null;
    hold_time_sessions?: number | null;
  } | null;
  /** R22.5: Shares plan when symbol qualifies (recommendation only). */
  shares_plan?: SharesPlan | null;
  /** R23.0: Current share position for this symbol (if any). Request-time only. */
  shares_position?: SharePosition | null;
  /** R22.7: Request-time inputs fingerprint (Universe vs Recompute verification). Not persisted. */
  as_of_inputs?: {
    evaluation_run_id?: string | null;
    pipeline_timestamp?: string | null;
    quote_as_of?: string | null;
    candles_as_of?: string | null;
    orats_as_of?: string | null;
    config_hash?: string | null;
  } | null;
  /** R22.7: Sample of contracts rejected due to delta (for reasons_explained). */
  sample_rejected_due_to_delta?: Array<Record<string, unknown>>;
  /** R23.1: Request-time only. Best delta miss vs band when rejected due to delta. Not persisted. */
  delta_diagnostics?: DeltaDiagnostics | null;
  /** R23.2: Per-symbol delta band override when present (for "Override active" badge and advanced form). */
  delta_override?: { delta_lo: number; delta_hi: number; updated_at_utc?: string } | null;
  /** R24.0: Options position sizing (request-time only; not persisted). */
  options_sizing?: OptionsSizing | null;
  /** R24.0: Next action badge: ENTRY | HOLD | CLOSE | ROLL | REDUCE | NONE. Request-time only. */
  next_action_code?: "ENTRY" | "HOLD" | "CLOSE" | "ROLL" | "REDUCE" | "NONE" | null;
  /** R25.2: Shares exit signal (request-time only; never persisted). Safe labels only. */
  shares_exit_hit_type?: "TARGET" | "STOP" | null;
  shares_exit_reason_safe?: string | null;
  shares_exit_last_price?: number | null;
  shares_exit_target_price?: number | null;
  shares_exit_stop_price?: number | null;
  shares_exit_as_of_ts?: string | null;
  /** R25.3: EOD-biased eligibility; request-time only. */
  cadence_mode?: string | null;
  eligibility_as_of_ts?: string | null;
  /** R25.3: Options position lifecycle (tracked CSP/CC); request-time only. */
  options_lifecycle?: {
    pct_max_profit?: number | null;
    dte?: number | null;
    mark_value?: number | null;
    mark_source?: string | null;
    mark_age_sec?: number | null;
    assignment_risk?: { active?: boolean; reason_code?: string | null };
    roll_window?: { active?: boolean; dte?: number | null };
    recommended_action_code?: "CLOSE" | "ROLL" | "HOLD" | null;
    recommended_by?: string | null;
    roll_window_threshold_dte?: number | null;
    roll_reason_codes?: string[] | null;
  } | null;
  /** R24.5: Earnings advisory (hero pill + risk flags). Advisory only; never blocks. Safe values only (OK/Unavailable/Stale). */
  earnings?: {
    earnings_days?: number | null;
    earnings_block?: boolean | null;
    note?: string | null;
    earnings_next_date?: string | null;
    earnings_annc_tod?: "AMC" | "BMO" | "Unknown" | string | null;
    implied_earnings_move_pct?: number | null;
    earnings_data_status?: "OK" | "Unavailable" | "Stale" | string | null;
    earnings_as_of?: string | null;
  } | null;
}

/** R24.0: Options sizing block (codes only; no FAIL_/WARN_ in notes_codes). */
export interface OptionsSizing {
  basis: "OK" | "INSUFFICIENT_DATA" | "NO_SELECTED_CANDIDATE";
  suggested_contracts: number | null;
  required_cash: number | null;
  credit_estimate: number | null;
  risk_pct_used: number | null;
  notes_codes: string[];
}

/** R23.1/R23.2: Delta reject visibility — best_delta, miss, direction (code-only), best_candidate. Request-time only. */
export interface DeltaDiagnostics {
  band_min: number;
  band_max: number;
  best_delta: number;
  miss: number;
  direction: "BELOW_BAND" | "ABOVE_BAND" | "IN_BAND";
  best_candidate?: {
    strike?: number | null;
    expiry?: string | null;
    dte?: number | null;
    bid?: number | null;
    ask?: number | null;
    spread?: number | null;
    contract_key?: string | null;
    option_symbol?: string | null;
  };
}

/** R22.5/R23.3: Shares plan (recommendation only; no order placement). Request-time only; not persisted. */
export interface SharesPlan {
  symbol?: string;
  /** R23.3: code-only; UI maps to safe text. */
  eligible?: boolean;
  /** R23.3: code-only reason_codes (e.g. SHARES_ELIGIBLE, NOT_NEAR_SUPPORT). Backend may return eligibility_codes. */
  reason_codes?: string[];
  eligibility_codes?: string[];
  spot?: number | null;
  /** R23.3: basis = DAILY_SUPPORT | WEEKLY_SUPPORT | BOTH. */
  entry_zone?: { low?: number | null; high?: number | null; basis?: string };
  /** R23.3: stop as { price, basis } (e.g. WEEKLY_SUPPORT_MINUS_ATR). */
  stop?: number | null | { price?: number | null; basis?: string };
  targets?: { t1?: number | null; t2?: number | null; t3?: number | null; basis?: string };
  invalidation?: number | null;
  hold_time_estimate?: {
    sessions?: number;
    basis_key?: string;
    hold_time_basis?: string | null;
    hold_time_atr?: number | null;
    hold_time_distance_to_t1?: number | null;
    hold_time_sessions?: number | null;
  };
  /** R23.3: hold_time with method (e.g. ATR_DISTANCE). */
  hold_time?: { sessions_to_t1?: number; sessions_to_t2?: number | null; method?: string };
  /** R23.3: sizing block; basis ACCOUNT_RISK | INSUFFICIENT_DATA. */
  sizing?: {
    suggested_shares?: number | null;
    suggested_cost?: number | null;
    max_loss?: number | null;
    risk_pct_used?: number | null;
    basis?: string;
  };
  confidence_score?: number | null;
  why_recommended?: string | null;
  support_resistance?: Record<string, { support?: number | null; resistance?: number | null; bar_count?: number | null; as_of?: string; method?: string } | null>;
  indicators_used?: Record<string, unknown>;
  as_of_inputs?: Record<string, unknown>;
}
