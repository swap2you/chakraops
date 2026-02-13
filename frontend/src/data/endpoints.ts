/**
 * Phase 8.7: API path constants for LIVE mode.
 * Backend may not expose all; stubs/TODOs where missing.
 */
const BASE = "";

export const ENDPOINTS = {
  dailyOverview: `${BASE}/api/view/daily-overview`,
  positions: `${BASE}/api/view/positions`,
  alerts: `${BASE}/api/view/alerts`,
  decisionHistory: `${BASE}/api/view/decision-history`,
  /** Optional; if absent, LIVE getTradePlan returns null. */
  tradePlan: `${BASE}/api/view/trade-plan`,
  healthz: `${BASE}/api/healthz`,
  /** Phase 10: market phase, last_market_check, last_evaluated_at, evaluation_attempted, evaluation_emitted */
  marketStatus: `${BASE}/api/market-status`,
  /** Phase 12: last_run_at, next_run_at, cadence_minutes, symbols_evaluated, trades_found, blockers_summary */
  opsStatus: `${BASE}/api/ops/status`,
  /** Route manifest: list of { path, methods, name } for /api/ routes only */
  routes: `${BASE}/api/ops/routes`,
  /** ORATS data health: status (OK/DEGRADED/DOWN), last_success_at, entitlement */
  dataHealth: `${BASE}/api/ops/data-health`,
  /** Pull fresh ORATS data; returns fetched_at + latency. 503 if ORATS fails. */
  refreshLiveData: `${BASE}/api/ops/refresh-live-data`,
  evaluate: `${BASE}/api/ops/evaluate`,
  evaluateStatus: `${BASE}/api/ops/evaluate`,
  symbolDiagnostics: `${BASE}/api/view/symbol-diagnostics`,
  universe: `${BASE}/api/view/universe`,
  /** System snapshot: summary of state without ORATS calls */
  snapshot: `${BASE}/api/ops/snapshot`,
  /** Universe evaluation: batch evaluation results with per-symbol data (in-memory cache) */
  universeEvaluation: `${BASE}/api/view/universe-evaluation`,
  /** Trigger immediate universe evaluation */
  evaluateNow: `${BASE}/api/ops/evaluate-now`,
  /** Alerts from evaluation (ELIGIBLE, EARNINGS_SOON, LIQUIDITY_WARN, etc.) */
  evaluationAlerts: `${BASE}/api/view/evaluation-alerts`,
  /** Send notification to Slack */
  notifySlack: `${BASE}/api/ops/notify/slack`,
  /** Phase 7.3: Send trade alert to Slack (symbol only; requires tier A/B, severity READY/NOW) */
  sendTradeAlert: `${BASE}/api/ops/send-trade-alert`,
  /** Strategy overview markdown (read-only) */
  strategyOverview: `${BASE}/api/view/strategy-overview`,
  /** Evaluation pipeline doc markdown (docs/EVALUATION_PIPELINE.md) */
  pipelineDoc: `${BASE}/api/view/pipeline-doc`,
  /** OpenAI TTS proxy: POST { text, voice? } → audio/mpeg */
  ttsSpeech: `${BASE}/api/tts/speech`,
  
  // ============================================================================
  // EVALUATION RUN PERSISTENCE ENDPOINTS (new)
  // ============================================================================
  
  /** Latest COMPLETED evaluation run - all screens should use this for truth */
  evaluationLatest: `${BASE}/api/view/evaluation/latest`,
  /** List recent evaluation runs (for history page) */
  evaluationRuns: `${BASE}/api/view/evaluation/runs`,
  /** Get full details of a specific run: /api/view/evaluation/{run_id} */
  evaluationRun: (runId: string) => `${BASE}/api/view/evaluation/${runId}`,
  /** Current evaluation status (is running, current run_id, last completed) */
  evaluationStatusCurrent: `${BASE}/api/view/evaluation/status/current`,
  /** Scheduler status including nightly */
  schedulerStatus: `${BASE}/api/ops/scheduler-status`,
  /** Nightly scheduler status */
  nightlyStatus: `${BASE}/api/ops/nightly-status`,

  // ============================================================================
  // TRADE JOURNAL
  // ============================================================================
  /** List trades (newest first) */
  tradesList: `${BASE}/api/trades`,
  /** Single trade detail */
  tradeDetail: (tradeId: string) => `${BASE}/api/trades/${tradeId}`,
  /** Create trade */
  tradesCreate: `${BASE}/api/trades`,
  /** Update trade */
  tradeUpdate: (tradeId: string) => `${BASE}/api/trades/${tradeId}`,
  /** Delete trade */
  tradeDelete: (tradeId: string) => `${BASE}/api/trades/${tradeId}`,
  /** Add fill to trade */
  tradeFillsCreate: (tradeId: string) => `${BASE}/api/trades/${tradeId}/fills`,
  /** Delete fill */
  tradeFillDelete: (tradeId: string, fillId: string) => `${BASE}/api/trades/${tradeId}/fills/${fillId}`,
  /** Export all trades CSV */
  tradesExportCsv: `${BASE}/api/trades/export.csv`,
  /** Export single trade CSV */
  tradeExportCsv: (tradeId: string) => `${BASE}/api/trades/${tradeId}/export.csv`,
  /** Journal alerts (stop breached, target hit) */
  tradesAlerts: `${BASE}/api/trades/alerts`,

  // ============================================================================
  // PHASE 6: ALERTING (alert log + Slack status)
  // ============================================================================
  /** Phase 6: Recent alert log (sent + suppressed) */
  alertLog: `${BASE}/api/view/alert-log`,
  /** Phase 2C: Lifecycle log (position directives) */
  lifecycleLog: `${BASE}/api/view/lifecycle-log`,
  /** Phase 6: Slack configured? */
  alertingStatus: `${BASE}/api/ops/alerting-status`,

  // ============================================================================
  // PHASE 3: PORTFOLIO & RISK INTELLIGENCE
  // ============================================================================
  /** Portfolio summary */
  portfolioSummary: `${BASE}/api/portfolio/summary`,
  /** Portfolio exposure (group_by=symbol|sector) */
  portfolioExposure: (groupBy: string) => `${BASE}/api/portfolio/exposure?group_by=${groupBy}`,
  /** Risk profile GET */
  portfolioRiskProfile: `${BASE}/api/portfolio/risk-profile`,
  /** Risk profile PUT */
  portfolioRiskProfilePut: `${BASE}/api/portfolio/risk-profile`,

  // ============================================================================
  // PHASE 2A: DASHBOARD OPPORTUNITIES (RANKED)
  // ============================================================================
  /** Ranked opportunities for dashboard (include_blocked for Phase 3) */
  dashboardOpportunities: `${BASE}/api/dashboard/opportunities`,

  // ============================================================================
  // PHASE 2B: SYMBOL INTELLIGENCE (TICKER PAGE)
  // ============================================================================
  /** Symbol explain: gates, band, strategy, capital */
  symbolExplain: (symbol: string) => `${BASE}/api/symbols/${encodeURIComponent(symbol)}/explain`,
  /** Top 3 contract candidates */
  symbolCandidates: (symbol: string) => `${BASE}/api/symbols/${encodeURIComponent(symbol)}/candidates`,
  /** Stock targets GET */
  symbolTargets: (symbol: string) => `${BASE}/api/symbols/${encodeURIComponent(symbol)}/targets`,
  /** Stock targets PUT */
  symbolTargetsPut: (symbol: string) => `${BASE}/api/symbols/${encodeURIComponent(symbol)}/targets`,
  /** Company metadata */
  symbolCompany: (symbol: string) => `${BASE}/api/symbols/${encodeURIComponent(symbol)}/company`,

  // ============================================================================
  // PHASE 1: ACCOUNTS & CAPITAL AWARENESS
  // ============================================================================
  /** List all accounts */
  accountsList: `${BASE}/api/accounts`,
  /** Get default account */
  accountsDefault: `${BASE}/api/accounts/default`,
  /** Create account */
  accountsCreate: `${BASE}/api/accounts`,
  /** Update account */
  accountUpdate: (accountId: string) => `${BASE}/api/accounts/${accountId}`,
  /** Set default account */
  accountSetDefault: (accountId: string) => `${BASE}/api/accounts/${accountId}/set-default`,
  /** CSP sizing for account + strike */
  accountCspSizing: (accountId: string) => `${BASE}/api/accounts/${accountId}/csp-sizing`,

  // ============================================================================
  // PHASE 1: TRACKED POSITIONS (MANUAL EXECUTION)
  // ============================================================================
  /** List tracked positions */
  trackedPositions: `${BASE}/api/positions/tracked`,
  /** Manual execute (create tracked position) */
  manualExecute: `${BASE}/api/positions/manual-execute`,
  /** Phase 4: Single position detail (includes exit if any) */
  positionDetail: (positionId: string) => `${BASE}/api/positions/tracked/${encodeURIComponent(positionId)}`,
  /** Phase 5: Auto-derive data sufficiency for symbol */
  symbolDataSufficiency: (symbol: string) => `${BASE}/api/symbols/${encodeURIComponent(symbol)}/data-sufficiency`,
  /** Phase 4: Log exit for position (POST) */
  positionLogExit: (positionId: string) => `${BASE}/api/positions/${encodeURIComponent(positionId)}/exit`,

  // ============================================================================
  // PHASE 4: DECISION QUALITY (POST-TRADE INTELLIGENCE)
  // ============================================================================
  /** Outcome summary: Win/Scratch/Loss, avg time in trade, capital days */
  decisionQualitySummary: `${BASE}/api/decision-quality/summary`,
  /** Strategy health: CSP/CC/STOCK Win %, Loss %, avg duration, Abort % */
  decisionQualityStrategyHealth: `${BASE}/api/decision-quality/strategy-health`,
  /** Exit discipline: % aligned with lifecycle, manual overrides */
  decisionQualityExitDiscipline: `${BASE}/api/decision-quality/exit-discipline`,
  /** Band × Outcome matrix */
  decisionQualityBandOutcome: `${BASE}/api/decision-quality/band-outcome`,
  /** Abort effectiveness */
  decisionQualityAbortEffectiveness: `${BASE}/api/decision-quality/abort-effectiveness`,
} as const;
