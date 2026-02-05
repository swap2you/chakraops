import type { DailyOverviewView, PositionView, TradePlanView, AlertsView, DecisionRecord } from "@/types/views";
import dailyOverviewJson from "@/mock/dailyOverview.json";
import positionsJson from "@/mock/positions.json";
import tradePlanJson from "@/mock/tradePlan.json";
import alertsJson from "@/mock/alerts.json";
import decisionHistoryJson from "@/mock/decisionHistory.json";
import { apiGet } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";

const isMock = (): boolean =>
  (import.meta as unknown as { env?: { VITE_DATA_MODE?: string } }).env?.VITE_DATA_MODE === "MOCK" ||
  (import.meta as unknown as { env?: { VITE_DATA_MODE?: string } }).env?.VITE_DATA_MODE === undefined;

export async function getDailyOverview(mode: "MOCK" | "LIVE"): Promise<DailyOverviewView | null> {
  if (mode === "MOCK" || isMock()) {
    return dailyOverviewJson as DailyOverviewView;
  }
  return apiGet<DailyOverviewView>(ENDPOINTS.dailyOverview);
}

export async function getPositions(mode: "MOCK" | "LIVE"): Promise<PositionView[]> {
  if (mode === "MOCK" || isMock()) {
    return positionsJson as PositionView[];
  }
  const raw = await apiGet<PositionView[]>(ENDPOINTS.positions);
  return Array.isArray(raw) ? raw : [];
}

export async function getTradePlan(mode: "MOCK" | "LIVE"): Promise<TradePlanView | null> {
  if (mode === "MOCK" || isMock()) {
    return tradePlanJson as TradePlanView;
  }
  try {
    return await apiGet<TradePlanView>(ENDPOINTS.tradePlan);
  } catch {
    // Optional endpoint; Dashboard still works without trade plan.
    return null;
  }
}

export async function getAlerts(mode: "MOCK" | "LIVE"): Promise<AlertsView | null> {
  if (mode === "MOCK" || isMock()) {
    return alertsJson as AlertsView;
  }
  return apiGet<AlertsView>(ENDPOINTS.alerts);
}

/** Phase 8: Decision audit — chronological list of past decisions (read-only). */
export async function getDecisionHistory(mode: "MOCK" | "LIVE"): Promise<DecisionRecord[]> {
  if (mode === "MOCK" || isMock()) {
    return decisionHistoryJson as DecisionRecord[];
  }
  const raw = await apiGet<DecisionRecord[]>(ENDPOINTS.decisionHistory);
  return Array.isArray(raw) ? raw : [];
}
