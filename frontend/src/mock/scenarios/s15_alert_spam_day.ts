import type { ScenarioBundle, AlertsView } from "@/types/views";

const dailyOverview = {
  date: "2026-02-12", run_mode: "DRY_RUN", config_frozen: true, freeze_violation_changed_keys: [] as string[],
  regime: "NEUTRAL", regime_reason: "VIX in range", symbols_evaluated: 52, selected_signals: 0, trades_ready: 0, no_trade: true,
  why_summary: "No READY setup.", top_blockers: [] as Array<{ code: string; count: number }>, risk_posture: "CONSERVATIVE",
  links: { latest_decision_ts: "2026-02-12T14:00:00Z" },
};

const positions: ScenarioBundle["positions"] = [];

const items: AlertsView["items"] = Array.from({ length: 14 }, (_, i) => ({
  level: i % 3 === 0 ? "info" : i % 3 === 1 ? "warning" : "error",
  code: `CODE_${i}`,
  message: `Message ${i}`,
  ...(i % 2 === 0 && i < 6 ? { symbol: "SPY", position_id: `pos-${i}` } : {}),
}));

const alerts: AlertsView = { as_of: "2026-02-12T14:00:00Z", items };

const decisionHistory: ScenarioBundle["decisionHistory"] = [
  { date: "2026-02-12", evaluated_at: "2026-02-12T14:00:00Z", outcome: "NO_TRADE", rationale: "No READY setup.", overview: dailyOverview, trade_plan: null, positions },
];

export const bundle: ScenarioBundle = { dailyOverview, tradePlan: null, positions, alerts, decisionHistory };
