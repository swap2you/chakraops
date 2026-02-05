/** S1: TRADE_READY_CLEAN — Decision TRADE, execution_status READY, regime allowed, 0–1 actionable alerts */
import type { ScenarioBundle } from "@/types/views";

const dailyOverview = {
  date: "2026-02-01",
  run_mode: "DRY_RUN",
  config_frozen: true,
  freeze_violation_changed_keys: [] as string[],
  regime: "NEUTRAL",
  regime_reason: "VIX in range",
  symbols_evaluated: 52,
  selected_signals: 1,
  trades_ready: 1,
  no_trade: false,
  why_summary: "1 safe trade available (SPY CSP). Regime allowed, risk posture aligned.",
  top_blockers: [] as Array<{ code: string; count: number }>,
  risk_posture: "CONSERVATIVE",
  links: { latest_decision_ts: "2026-02-01T14:00:00Z" },
};

const tradePlan = {
  decision_ts: "2026-02-01T14:00:00Z",
  symbol: "SPY",
  strategy_type: "CSP",
  proposal: { symbol: "SPY", strategy_type: "CSP", expiry: "2026-04-18", strikes: [450], contracts: 1, credit_estimate: 260, max_loss: 520 },
  execution_status: "READY",
  user_acknowledged: false,
  execution_notes: "",
  exit_plan: {},
  computed_targets: { t1: 104, t2: 78, t3: 39 },
  blockers: [] as string[],
};

const positions = [
  { position_id: "pos-1", symbol: "SPY", strategy_type: "CSP", lifecycle_state: "OPEN", opened: "2026-01-15", expiry: "2026-03-21", strike: 450, contracts: 1, entry_credit: 250, last_mark: null as number | null, dte: 45, unrealized_pnl: null as number | null, realized_pnl: 0, max_loss_estimate: 500, profit_targets: { t1: 100, t2: 75, t3: 37.5 }, notes: "", needs_attention: false, attention_reasons: [] as string[] },
];

const alerts = { as_of: "2026-02-01T14:00:00Z", items: [{ level: "info", code: "TARGET_1_HIT", message: "QQQ near T1", symbol: "QQQ", position_id: "pos-2" }] };

const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-02-01", evaluated_at: "2026-02-01T14:00:00Z", outcome: "TRADE" as const, rationale: "1 safe trade available (SPY CSP). Regime allowed, risk posture aligned.", overview: dailyOverview, trade_plan: tradePlan, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan, positions, alerts, decisionHistory };
