/** S18: STRESS_250_HISTORY_50_POSITIONS — 250+ decision records, 50+ positions; render and filter must stay responsive */
import type { ScenarioBundle, PositionView, DecisionRecord } from "@/types/views";

const baseDate = new Date("2026-01-01");
const dailyOverview = {
  date: "2026-02-15",
  run_mode: "DRY_RUN",
  config_frozen: true,
  freeze_violation_changed_keys: [] as string[],
  regime: "NEUTRAL",
  regime_reason: "VIX in range",
  symbols_evaluated: 52,
  selected_signals: 0,
  trades_ready: 0,
  no_trade: true,
  why_summary: "No READY setup.",
  top_blockers: [] as Array<{ code: string; count: number }>,
  risk_posture: "CONSERVATIVE",
  links: { latest_decision_ts: "2026-02-15T14:00:00Z" },
};

const symbols = ["SPY", "QQQ", "AAPL", "NVDA", "MSFT", "GOOGL", "META", "AMZN"];
const positions: PositionView[] = Array.from({ length: 52 }, (_, i) => ({
  position_id: `pos-${i}`,
  symbol: symbols[i % symbols.length],
  strategy_type: "CSP",
  lifecycle_state: i % 5 === 0 ? "CLOSED" : "OPEN",
  opened: "2026-01-01",
  expiry: "2026-03-21",
  strike: 400 + i,
  contracts: 1,
  entry_credit: 200 + i,
  last_mark: i % 2 === 0 ? 80 : null,
  dte: i % 5 === 0 ? null : 40 - (i % 20),
  unrealized_pnl: null,
  realized_pnl: i % 5 === 0 ? 10 - i : 0,
  max_loss_estimate: 500,
  profit_targets: { t1: 100, t2: 75, t3: 37.5 },
  notes: "",
  needs_attention: i % 7 === 0,
  attention_reasons: i % 7 === 0 ? ["TARGET_1_HIT"] : [],
}));

const decisionHistory: DecisionRecord[] = Array.from({ length: 255 }, (_, i) => {
  const d = new Date(baseDate);
  d.setDate(d.getDate() + i);
  const dateStr = d.toISOString().slice(0, 10);
  const outcome = i % 3 === 0 ? "TRADE" : i % 3 === 1 ? "NO_TRADE" : "RISK_HOLD";
  return {
    date: dateStr,
    evaluated_at: `${dateStr}T14:00:00Z`,
    outcome: outcome as DecisionRecord["outcome"],
    rationale: outcome === "TRADE" ? "1 safe trade available." : "No READY setup.",
    overview: { ...dailyOverview, date: dateStr, links: { latest_decision_ts: `${dateStr}T14:00:00Z` } },
    trade_plan: null,
    positions: positions.slice(0, 2),
  };
});

export const bundle: ScenarioBundle = { dailyOverview, tradePlan: null, positions, alerts: { as_of: "2026-02-15T14:00:00Z", items: [] }, decisionHistory };
