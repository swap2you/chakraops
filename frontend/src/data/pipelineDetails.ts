/**
 * Pipeline Details – implementation-truthful data for the Pipeline page.
 * Matches chakraops/docs/EVALUATION_PIPELINE.md. Used for interactive stage cards.
 */

export interface PipelineInput {
  name: string;
  source: string;
}

export interface PipelineFailureMode {
  condition: string;
  result: string;
  code?: string;
}

export interface PipelineWhereToVerify {
  label: string;
  path: string;
}

export interface PipelineStageDetail {
  id: string;
  stageNumber: number;
  title: string;
  purpose: string;
  inputs: PipelineInput[];
  outputs: string[];
  failureModes: PipelineFailureMode[];
  whereToVerify: PipelineWhereToVerify[];
}

export const PIPELINE_DETAILS: PipelineStageDetail[] = [
  {
    id: "universe",
    stageNumber: 1,
    title: "Universe",
    purpose:
      "Define the set of symbols evaluated in each run. The system does not add or remove symbols automatically.",
    inputs: [
      { name: "Symbol list", source: "config/universe.csv (symbol, strategy_hint, notes)" },
      { name: "Strategy hint", source: "Same file (optional; influences CSP/CC focus)" },
    ],
    outputs: ["List of symbols passed to the evaluator (one batch per run)"],
    failureModes: [
      { condition: "Empty universe file", result: "No symbols evaluated; run completes with zero results" },
      { condition: "Invalid symbol format", result: "Symbol skipped; warning in logs" },
      { condition: "Duplicate entries", result: "Deduplicated; first occurrence kept" },
    ],
    whereToVerify: [
      { label: "Config", path: "chakraops/config/universe.csv" },
      { label: "API", path: "GET /api/view/universe" },
      { label: "Run JSON", path: "out/evaluations/{run_id}.json → symbols[] length" },
    ],
  },
  {
    id: "regime",
    stageNumber: 2,
    title: "Market Regime",
    purpose:
      "Global filter from index (SPY/QQQ) technicals. All symbols see the same regime. Used to cap scores and block CSP in RISK_OFF.",
    inputs: [
      { name: "Index data (SPY, QQQ)", source: "Persisted snapshot: close, EMA(20), EMA(50), RSI(14), ATR(14)" },
      { name: "Regime persistence", source: "out/market/market_regime.json (one record per trading day)" },
    ],
    outputs: [
      "regime: RISK_ON | NEUTRAL | RISK_OFF",
      "Used in verdict resolution (e.g. RISK_OFF → HOLD, score cap 50) and Band availability",
    ],
    failureModes: [
      { condition: "Index data unavailable", result: "Defaults to NEUTRAL; warning in logs" },
      { condition: "RISK_OFF", result: "All scores capped at 50; CSP blocked", code: "REGIME_RISK_OFF" },
      { condition: "NEUTRAL", result: "Scores capped at 65; Band A unavailable" },
    ],
    whereToVerify: [
      { label: "Persistence", path: "out/market/market_regime.json → date, regime, inputs" },
      { label: "API", path: "GET /api/market-status → market_phase" },
      { label: "Run JSON", path: "Top-level regime, market_phase; symbols[].regime" },
    ],
  },
  {
    id: "quality",
    stageNumber: 3,
    title: "Stock Quality (Stage 1)",
    purpose:
      "Ensure minimum required equity data. Missing price is fatal. Missing bid/ask/volume may be waived if options liquidity is later confirmed (OPRA).",
    inputs: [
      { name: "Equity snapshot", source: "ORATS GET /datav2/strikes/options (underlying tickers)" },
      { name: "IV rank", source: "ORATS GET /datav2/ivrank (ivRank1m or ivPct1m)" },
      { name: "avg_volume", source: "Not available from ORATS; always in missing_fields, does not block" },
    ],
    outputs: [
      "Per symbol: price, bid, ask, volume, iv_rank, data_completeness, missing_fields, data_sources",
      "Stage 1 verdict: QUALIFIED | HOLD | BLOCKED | ERROR; stock_verdict_reason; stage1_score (0–100)",
    ],
    failureModes: [
      { condition: "No price data", result: "BLOCKED", code: "DATA_INCOMPLETE_FATAL: No price data" },
      { condition: "No equity snapshot returned", result: "ERROR" },
      { condition: "Fatal missing fields", result: "HOLD", code: "DATA_INCOMPLETE_FATAL" },
      { condition: "Only intraday fields missing, market CLOSED", result: "Non-fatal; may proceed", code: "DATA_INCOMPLETE_INTRADAY" },
      { condition: "avg_volume missing", result: "Never blocks; in missing_fields" },
    ],
    whereToVerify: [
      { label: "Run JSON", path: "symbols[].price, missing_fields, data_completeness, stage_reached" },
      { label: "API", path: "GET /api/view/evaluation/latest → symbols[]" },
      { label: "Code", path: "app.core.eval.staged_evaluator.evaluate_stage1, verdict_resolver.classify_data_incompleteness" },
    ],
  },
  {
    id: "eligibility",
    stageNumber: 4,
    title: "Strategy Eligibility",
    purpose:
      "Block new CSP if open CSP exists for symbol; block second CC if open CC exists. Apply regime-based blocks (e.g. no CSP in RISK_OFF).",
    inputs: [
      { name: "Open positions", source: "Journal (list_trades, remaining_qty > 0)" },
      { name: "Current regime", source: "Stage 2 output" },
      { name: "Strategy type", source: "Config / evaluation focus (CSP or CC)" },
    ],
    outputs: [
      "position_open (bool), position_reason (e.g. POSITION_ALREADY_OPEN)",
      "verdict_reason_code = POSITION_BLOCKED when blocked",
    ],
    failureModes: [
      { condition: "Open CSP for symbol", result: "New CSP BLOCKED", code: "POSITION_ALREADY_OPEN / POSITION_BLOCKED" },
      { condition: "Open CC for symbol", result: "Second CC BLOCKED", code: "POSITION_BLOCKED" },
      { condition: "RISK_OFF + CSP", result: "BLOCKED", code: "REGIME_RISK_OFF" },
      { condition: "Exposure cap exceeded", result: "BLOCKED", code: "EXPOSURE_BLOCKED" },
    ],
    whereToVerify: [
      { label: "Run JSON", path: "symbols[].position_open, position_reason, verdict_reason_code; exposure_summary" },
      { label: "API", path: "GET /api/view/positions, GET /api/trades" },
      { label: "Code", path: "app.core.eval.position_awareness, verdict_resolver.resolve_final_verdict" },
    ],
  },
  {
    id: "liquidity",
    stageNumber: 5,
    title: "Options Liquidity (Stage 2)",
    purpose:
      "Confirm usable option contracts: chain exists, and after OPRA lookup bid/ask/OI meet liquidity rules. Enables waiver of upstream stock-level bid/ask gaps when options liquidity is confirmed.",
    inputs: [
      { name: "Strike grid", source: "ORATS GET /datav2/strikes or /datav2/live/strikes" },
      { name: "Option liquidity", source: "ORATS GET /datav2/strikes/options (OCC symbols)" },
    ],
    outputs: [
      "liquidity_ok, liquidity_reason, liquidity_grade; options_available, options_reason",
      "When OPRA confirms: waiver_reason = DERIVED_FROM_OPRA",
    ],
    failureModes: [
      { condition: "No options chain", result: "HOLD/BLOCKED; no contract" },
      { condition: "No contracts meeting criteria", result: "HOLD" },
      { condition: "DATA_INCOMPLETE (chain fields missing)", result: "HOLD" },
      { condition: "Market CLOSED + intraday chain gaps", result: "Non-fatal" },
      { condition: "OPRA confirms at least one valid put", result: "Waiver; liquidity_ok may be true", code: "DERIVED_FROM_OPRA" },
    ],
    whereToVerify: [
      { label: "Run JSON", path: "symbols[].liquidity_ok, liquidity_reason, waiver_reason, selected_contract, stage_reached" },
      { label: "API", path: "GET /api/view/evaluation/latest, GET /api/view/symbol-diagnostics" },
      { label: "Code", path: "app.core.eval.staged_evaluator.evaluate_stage2, chain_provider" },
    ],
  },
  {
    id: "construction",
    stageNumber: 6,
    title: "Trade Construction",
    purpose:
      "For symbols that passed liquidity, select the recommended contract: target delta (~-0.25 CSP), DTE window (e.g. 21–45), liquidity grade threshold.",
    inputs: [
      { name: "Options chain", source: "Stage 2 fetch" },
      { name: "Target delta", source: "Constants (e.g. -0.25 CSP; tolerance 0.10)" },
      { name: "DTE window", source: "TARGET_DTE_MIN=21, TARGET_DTE_MAX=45" },
      { name: "Liquidity threshold", source: "MIN_LIQUIDITY_GRADE, MIN_OPEN_INTEREST, MAX_SPREAD_PCT" },
    ],
    outputs: [
      "selected_contract (strike, expiry, delta, bid/ask, OI, liquidity_grade, selection_reason)",
      "selected_expiration; candidate_trades[]",
    ],
    failureModes: [
      { condition: "No contracts in DTE window", result: "ELIGIBLE possible but no specific contract" },
      { condition: "No strike near target delta", result: "Best available selected; deviation noted" },
      { condition: "Liquidity below threshold", result: "Contract not selected; HOLD" },
    ],
    whereToVerify: [
      { label: "Run JSON", path: "symbols[].selected_contract, selected_expiration, candidate_trades" },
      { label: "API", path: "GET /api/view/symbol-diagnostics → candidate trades, selected contract" },
      { label: "Code", path: "app.core.options.contract_selector.select_contract" },
    ],
  },
  {
    id: "scoring",
    stageNumber: 7,
    title: "Score & Band",
    purpose:
      "Assign a relative score (0–100) and confidence band (A/B/C) for sorting and capital hints. Score is not a probability; Band reflects data quality and regime.",
    inputs: [
      { name: "Prior stages", source: "Regime, data_completeness, liquidity, verdict" },
      { name: "Stage 1 score", source: "staged_evaluator (baseline + regime/IV/completeness)" },
      { name: "Stage 2 result", source: "Liquidity and selection success" },
    ],
    outputs: [
      "score (0–100); confidence; capital_hint: { band, suggested_capital_pct }",
      "Verdict: ELIGIBLE | HOLD | BLOCKED (after verdict resolution)",
    ],
    failureModes: [
      { condition: "HOLD/BLOCKED verdict", result: "Band C" },
      { condition: "RISK_OFF", result: "Score capped at 50" },
      { condition: "NEUTRAL", result: "Score capped at 65; Band A unavailable" },
      { condition: "Data incomplete (even if waived)", result: "Score penalized; cap at 60 if severe" },
    ],
    whereToVerify: [
      { label: "Run JSON", path: "symbols[].score, verdict, primary_reason, verdict_reason_code, capital_hint" },
      { label: "API", path: "GET /api/view/evaluation/latest → symbols[]; counts: eligible, shortlisted, stage1_pass, stage2_pass" },
      { label: "Code", path: "app.core.eval.confidence_band.compute_confidence_band, verdict_resolver.resolve_final_verdict" },
    ],
  },
];
