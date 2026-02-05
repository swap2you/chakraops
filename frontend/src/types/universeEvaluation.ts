/**
 * Types for Universe Evaluation and Alerts
 */

export interface CandidateTrade {
  strategy: string; // CSP, CC, HOLD
  expiry: string | null;
  strike: number | null;
  delta: number | null;
  credit_estimate: number | null;
  max_loss: number | null;
  why_this_trade: string;
}

/**
 * Data quality status for a field
 */
export type DataQuality = "VALID" | "MISSING" | "ERROR";

/**
 * Tri-state field value with quality metadata
 */
export interface FieldValue<T> {
  value: T | null;
  quality: DataQuality;
  reason?: string;
  field_name?: string;
}

/**
 * Evaluation stage in 2-stage pipeline
 */
export type EvaluationStage = "NOT_STARTED" | "STAGE1_ONLY" | "STAGE2_CHAIN";

/**
 * Selected contract from stage 2 evaluation
 */
export interface SelectedContract {
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
  criteria_results: Record<string, boolean>;
}

export interface SymbolEvaluationResult {
  symbol: string;
  source: string;
  // Stock data (null if MISSING - NOT 0)
  price: number | null;
  bid: number | null;
  ask: number | null;
  volume: number | null;
  avg_volume: number | null;
  // Verdict
  verdict: "ELIGIBLE" | "HOLD" | "BLOCKED" | "UNKNOWN";
  primary_reason: string;
  confidence: number;
  score: number; // 0-100, capped at 60 if DATA_INCOMPLETE
  // Context
  regime: string | null;
  risk: string | null;
  liquidity_ok: boolean;
  liquidity_reason: string;
  earnings_blocked: boolean;
  earnings_days: number | null;
  options_available: boolean;
  options_reason: string;
  // Gates
  gates: Array<{ name: string; status: string; reason: string }>;
  blockers: string[];
  // Candidate trades
  candidate_trades: CandidateTrade[];
  // Metadata
  fetched_at: string | null;
  error: string | null;
  // Data quality fields - tracks which fields are VALID vs MISSING
  data_completeness?: number; // 0.0 to 1.0
  missing_fields?: string[]; // List of field names that are MISSING
  data_quality_details?: Record<string, DataQuality>; // field_name -> quality
  // 2-Stage pipeline fields
  stage_reached?: EvaluationStage; // Stage reached in pipeline
  selected_contract?: SelectedContract; // Selected contract from stage 2
  selected_expiration?: string; // ISO date string of selected expiration
  // Phase 8: Strategy explainability
  rationale?: StrategyRationale | null;
  // Phase 9: Position awareness
  position_open?: boolean;
  position_reason?: string | null;
  // Phase 10: Confidence band and capital hint
  capital_hint?: { band: string; suggested_capital_pct: number } | null;
}

/** Phase 8: Human-readable verdict explanation from evaluation run */
export interface StrategyRationale {
  summary: string;
  bullets: string[];
  failed_checks: string[];
  data_warnings: string[];
}

/**
 * Run source - how the evaluation was triggered
 */
export type EvaluationSource = "manual" | "scheduled" | "nightly" | "api";

export interface UniverseEvaluationCounts {
  total: number;
  evaluated: number;
  eligible: number;
  shortlisted: number;
}

export interface UniverseEvaluationResult {
  evaluation_state: "IDLE" | "RUNNING" | "COMPLETED" | "FAILED";
  evaluation_state_reason: string;
  last_evaluated_at: string | null;
  duration_seconds?: number;
  counts: UniverseEvaluationCounts;
  symbols: SymbolEvaluationResult[];
  alerts_count: number;
  errors?: string[];
}

export type AlertType = "ELIGIBLE" | "TARGET_HIT" | "DATA_STALE" | "DATA_INCOMPLETE" | "EARNINGS_SOON" | "LIQUIDITY_WARN";
export type AlertSeverity = "INFO" | "WARN" | "ERROR";

export interface EvaluationAlert {
  id: string;
  type: AlertType;
  symbol: string;
  message: string;
  severity: AlertSeverity;
  created_at: string;
  meta?: Record<string, unknown>;
}

export interface EvaluationAlertsResponse {
  alerts: EvaluationAlert[];
  count: number;
  last_generated_at: string | null;
  reason?: string;
}

export interface SlackNotifyRequest {
  channel?: string;
  text?: string;
  meta?: {
    symbol?: string;
    strategy?: string;
    expiry?: string;
    strike?: number;
    delta?: number;
    credit_estimate?: number;
    score?: number;
    reason?: string;
  };
}

export interface SlackNotifyResponse {
  sent: boolean;
  reason: string | null;
  /** HTTP status code from Slack (if failed) */
  status_code?: number | null;
  /** Response body from Slack (for debugging failures) */
  slack_response_body?: string | null;
}

export interface EvaluateNowResponse {
  started: boolean;
  reason: string;
  run_id: string | null;
}

// ============================================================================
// EVALUATION RUN PERSISTENCE TYPES
// ============================================================================

/**
 * Summary of an evaluation run (for listing)
 */
export interface EvaluationRunSummary {
  run_id: string;
  started_at: string;
  completed_at: string | null;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  duration_seconds: number;
  total: number;
  evaluated: number;
  eligible: number;
  shortlisted: number;
  stage1_pass?: number;
  stage2_pass?: number;
  holds?: number;
  blocks?: number;
  regime: string | null;
  risk_posture: string | null;
  market_phase: string | null;
  source?: EvaluationSource;
  error_summary: string | null;
  errors_count: number;
}

/**
 * Response from GET /api/view/evaluation/latest (single source of truth for read-only views).
 */
export interface EvaluationLatestResponse {
  has_completed_run: boolean;
  run_id: string | null;
  started_at?: string;
  completed_at: string | null;
  status: string; // COMPLETED | NO_RUNS | CORRUPTED | ERROR
  reason?: string;
  duration_seconds?: number;
  counts: {
    total: number;
    evaluated: number;
    eligible: number;
    shortlisted: number;
  };
  regime?: string | null;
  risk_posture?: string | null;
  market_phase?: string | null;
  top_candidates: SymbolEvaluationResult[];
  /** Full per-symbol list from persisted run; Dashboard/Universe use only this (no live recompute). */
  symbols?: SymbolEvaluationResult[];
  alerts_count: number;
  errors_count?: number;
  read_source?: string;
  /** True when persisted run was corrupt or read failed; UI must not hide. */
  backend_failure?: boolean;
}

/**
 * Response from GET /api/view/evaluation/runs
 */
export interface EvaluationRunsResponse {
  runs: EvaluationRunSummary[];
  count: number;
  latest_run_id: string | null;
  reason?: string;
}

/**
 * Response from GET /api/view/evaluation/{run_id}
 */
export interface EvaluationRunDetailResponse {
  found: boolean;
  run_id: string;
  reason?: string;
  // If found, includes all EvaluationRunFull fields
  started_at?: string;
  completed_at?: string | null;
  status?: string;
  duration_seconds?: number;
  total?: number;
  evaluated?: number;
  eligible?: number;
  shortlisted?: number;
  regime?: string | null;
  risk_posture?: string | null;
  market_phase?: string | null;
  symbols?: SymbolEvaluationResult[];
  top_candidates?: SymbolEvaluationResult[];
  alerts?: EvaluationAlert[];
  alerts_count?: number;
  errors?: string[];
  error_summary?: string | null;
}

/**
 * Response from GET /api/view/evaluation/status/current
 */
export interface EvaluationStatusCurrentResponse {
  is_running: boolean;
  current_run_id: string | null;
  evaluation_state: string;
  evaluation_state_reason: string;
  last_completed_run_id: string | null;
  last_completed_at: string | null;
}

/**
 * Build Slack message from trade data
 */
export function buildSlackMessage(data: {
  symbol: string;
  strategy: string;
  expiry?: string | null;
  strike?: number | null;
  delta?: number | null;
  credit_estimate?: number | null;
  score?: number;
  reason?: string;
}): string {
  const parts = [
    "ChakraOps",
    data.symbol,
    data.strategy,
    `exp ${data.expiry ?? "?"}`,
    `strike ${data.strike ?? "?"}`,
    `delta ${data.delta ?? "?"}`,
    `credit~ ${data.credit_estimate ?? "?"}`,
    `score ${data.score ?? "?"}`,
    `reason: ${(data.reason ?? "").slice(0, 50)}`,
  ];
  return parts.join(" | ");
}

/**
 * Get verdict badge color
 */
export function getVerdictColor(verdict: string): string {
  switch (verdict) {
    case "ELIGIBLE":
      return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
    case "HOLD":
      return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200";
    case "BLOCKED":
      return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
    default:
      return "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200";
  }
}

/**
 * Get alert type badge color
 */
export function getAlertTypeColor(type: AlertType): string {
  switch (type) {
    case "ELIGIBLE":
      return "bg-green-100 text-green-800";
    case "TARGET_HIT":
      return "bg-blue-100 text-blue-800";
    case "DATA_STALE":
      return "bg-red-100 text-red-800";
    case "DATA_INCOMPLETE":
      return "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300";
    case "EARNINGS_SOON":
      return "bg-orange-100 text-orange-800";
    case "LIQUIDITY_WARN":
      return "bg-yellow-100 text-yellow-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
}

/**
 * Format price with fallback - shows "Not provided by provider" for MISSING (null)
 * NOTE: 0 is a valid price and will display as "$0.00"
 */
export function formatPrice(price: number | null | undefined): string {
  if (price == null) return "Not provided by provider";
  return `$${price.toFixed(2)}`;
}

/**
 * Format volume with fallback - shows "Not provided by provider" for MISSING (null)
 * NOTE: 0 is a valid volume and will display as "0"
 */
export function formatVolume(volume: number | null | undefined): string {
  if (volume == null) return "Not provided by provider";
  if (volume >= 1_000_000) return `${(volume / 1_000_000).toFixed(1)}M`;
  if (volume >= 1_000) return `${(volume / 1_000).toFixed(1)}K`;
  return volume.toLocaleString();
}

/**
 * Format bid/ask with fallback - shows "Not provided by provider" for MISSING (null)
 * NOTE: 0 is a valid bid/ask and will display as "$0.00"
 */
export function formatBidAsk(value: number | null | undefined): string {
  if (value == null) return "Not provided by provider";
  return `$${value.toFixed(2)}`;
}

/**
 * Check if a field is MISSING (not just 0)
 */
export function isFieldMissing(
  value: number | null | undefined,
  dataQuality?: Record<string, DataQuality>,
  fieldName?: string
): boolean {
  // If we have explicit quality info, use it
  if (dataQuality && fieldName && fieldName in dataQuality) {
    return dataQuality[fieldName] === "MISSING";
  }
  // Fall back to null check
  return value === null || value === undefined;
}

/**
 * Format a reason that may contain DATA_INCOMPLETE
 */
export function formatReason(reason: string): { text: string; isDataIncomplete: boolean; missingFields: string[] } {
  const isDataIncomplete = reason.startsWith("DATA_INCOMPLETE");
  let missingFields: string[] = [];

  if (isDataIncomplete) {
    // Extract missing fields from reason like "DATA_INCOMPLETE - missing: bid, ask, volume"
    const match = reason.match(/missing:\s*([^-]+)/i);
    if (match) {
      missingFields = match[1].split(",").map((f) => f.trim());
    }
  }

  return { text: reason, isDataIncomplete, missingFields };
}

/**
 * Format evaluation stage for display
 */
export function formatStage(stage: EvaluationStage | undefined): { label: string; color: string; description: string } {
  switch (stage) {
    case "STAGE2_CHAIN":
      return {
        label: "Chain Evaluated",
        color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300",
        description: "Full chain analysis completed",
      };
    case "STAGE1_ONLY":
      return {
        label: "Stock Qualified",
        color: "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300",
        description: "Stock qualified, chain pending",
      };
    case "NOT_STARTED":
    default:
      return {
        label: "Not Started",
        color: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300",
        description: "Evaluation not started",
      };
  }
}

/**
 * Format liquidity grade for display
 */
export function formatLiquidityGrade(grade: string | undefined): { label: string; color: string } {
  switch (grade) {
    case "A":
      return { label: "A", color: "bg-emerald-500 text-white" };
    case "B":
      return { label: "B", color: "bg-blue-500 text-white" };
    case "C":
      return { label: "C", color: "bg-yellow-500 text-white" };
    case "D":
      return { label: "D", color: "bg-orange-500 text-white" };
    case "F":
    default:
      return { label: "F", color: "bg-red-500 text-white" };
  }
}

/**
 * Format selected contract for display
 */
export function formatSelectedContract(contract: SelectedContract | undefined): string | null {
  if (!contract?.contract) return null;
  const c = contract.contract;
  const parts = [
    c.option_type,
    `$${c.strike.toFixed(0)}`,
    c.expiration,
    c.delta !== null ? `δ${c.delta.toFixed(2)}` : "",
    c.bid !== null ? `$${c.bid.toFixed(2)}` : "",
  ].filter(Boolean);
  return parts.join(" ");
}

/**
 * Format evaluation source for display
 */
export function formatSource(source: EvaluationSource | undefined): { label: string; color: string; icon: string } {
  switch (source) {
    case "nightly":
      return {
        label: "Nightly",
        color: "bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300",
        icon: "🌙",
      };
    case "scheduled":
      return {
        label: "Scheduled",
        color: "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300",
        icon: "⏰",
      };
    case "api":
      return {
        label: "API",
        color: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300",
        icon: "🔌",
      };
    case "manual":
    default:
      return {
        label: "Manual",
        color: "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300",
        icon: "👤",
      };
  }
}
