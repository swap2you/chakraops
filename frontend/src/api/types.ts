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
// SystemHealthResponse — GET /api/healthz (public, not under /api/ui)
// =============================================================================

export interface SystemHealthResponse {
  ok: boolean;
  status?: string;
}

// =============================================================================
// DataHealthResponse — GET /api/ops/data-health
// =============================================================================

export interface DataHealthResponse {
  provider: string;
  status: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_error_at: string | null;
  last_error_reason: string | null;
  avg_latency_seconds: number | null;
  entitlement: string;
  effective_last_success_at: string | null;
}

// =============================================================================
// Symbol diagnostics extended (stage breakdown, liquidity)
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

export interface SymbolDiagnosticsResponseExtended extends SymbolDiagnosticsResponse {
  symbol_eligibility?: SymbolEligibilityDetail;
  liquidity?: SymbolLiquidityDetail;
}
