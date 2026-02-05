/**
 * Phase 8.5 / 8.7: Validator — scenario bundle (MOCK) and single views (LIVE). Returns warnings; does not throw.
 */
import type {
  ScenarioBundle,
  DecisionRecord,
  DailyOverviewView,
  PositionView,
  AlertsView,
} from "@/types/views";

export interface ValidationWarning {
  code: string;
  message: string;
  /** Affected record index (decisionHistory) or position_id or "overview" | "tradePlan" | "alerts" */
  affectedId?: string | number;
}

export function validateScenarioBundle(bundle: ScenarioBundle, _scenarioKey: string): ValidationWarning[] {
  const warnings: ValidationWarning[] = [];

  if (!bundle.dailyOverview && (bundle.decisionHistory?.length ?? 0) > 0) {
    warnings.push({ code: "MISSING_OVERVIEW", message: "Daily overview is null but history has records.", affectedId: "overview" });
  }
  if (bundle.dailyOverview) {
    const o = bundle.dailyOverview;
    if (o.symbols_evaluated > 500) {
      warnings.push({ code: "HIGH_SYMBOLS", message: `Very high symbols_evaluated (${o.symbols_evaluated}).`, affectedId: "overview" });
    }
    if (!o.date || !o.why_summary) {
      warnings.push({ code: "OVERVIEW_PARTIAL", message: "Daily overview missing date or why_summary.", affectedId: "overview" });
    }
  }

  if (bundle.tradePlan) {
    const t = bundle.tradePlan;
    if (!t.computed_targets || Object.keys(t.computed_targets).length === 0) {
      warnings.push({ code: "MISSING_TARGETS", message: "Trade plan has no computed_targets.", affectedId: "tradePlan" });
    }
    if (!t.symbol || !t.execution_status) {
      warnings.push({ code: "TRADE_PLAN_PARTIAL", message: "Trade plan missing symbol or execution_status.", affectedId: "tradePlan" });
    }
  }

  const history = bundle.decisionHistory ?? [];
  history.forEach((rec: DecisionRecord, i: number) => {
    if (rec.overview == null) {
      warnings.push({ code: "RECORD_PARTIAL_OVERVIEW", message: "Decision record has no overview (partial record).", affectedId: i });
    }
    if (!rec.date || !rec.evaluated_at) {
      warnings.push({ code: "RECORD_MISSING_DATE", message: "Decision record missing date or evaluated_at.", affectedId: i });
    }
  });

  if ((bundle.alerts?.items?.length ?? 0) > 20) {
    warnings.push({ code: "ALERT_VOLUME", message: `High alert count (${bundle.alerts!.items.length}).`, affectedId: "alerts" });
  }

  if ((bundle.positions?.length ?? 0) > 100) {
    warnings.push({ code: "POSITION_VOLUME", message: `High position count (${bundle.positions!.length}).`, affectedId: "positions" });
  }

  return warnings;
}

/** Phase 8.7: Validate daily overview (LIVE or MOCK). No throw. */
export function validateDailyOverview(view: DailyOverviewView | null): ValidationWarning[] {
  const warnings: ValidationWarning[] = [];
  if (!view) return warnings;
  if (view.symbols_evaluated > 500) {
    warnings.push({ code: "HIGH_SYMBOLS", message: `Very high symbols_evaluated (${view.symbols_evaluated}).`, affectedId: "overview" });
  }
  if (!view.date || !view.why_summary) {
    warnings.push({ code: "OVERVIEW_PARTIAL", message: "Daily overview missing date or why_summary.", affectedId: "overview" });
  }
  return warnings;
}

/** Phase 8.7: Validate positions list (LIVE or MOCK). No throw. */
export function validatePositions(positions: PositionView[] | null): ValidationWarning[] {
  const warnings: ValidationWarning[] = [];
  if (!positions) return warnings;
  if (positions.length > 100) {
    warnings.push({ code: "POSITION_VOLUME", message: `High position count (${positions.length}).`, affectedId: "positions" });
  }
  return warnings;
}

/** Phase 8.7: Validate alerts view (LIVE or MOCK). No throw. */
export function validateAlerts(view: AlertsView | null): ValidationWarning[] {
  const warnings: ValidationWarning[] = [];
  if (!view) return warnings;
  const count = view.items?.length ?? 0;
  if (count > 20) {
    warnings.push({ code: "ALERT_VOLUME", message: `High alert count (${count}).`, affectedId: "alerts" });
  }
  return warnings;
}

/** Phase 8.7: Validate decision history (LIVE or MOCK). No throw. */
export function validateDecisionHistory(records: DecisionRecord[] | null): ValidationWarning[] {
  const warnings: ValidationWarning[] = [];
  if (!records) return warnings;
  records.forEach((rec, i) => {
    if (rec.overview == null) {
      warnings.push({ code: "RECORD_PARTIAL_OVERVIEW", message: "Decision record has no overview (partial record).", affectedId: i });
    }
    if (!rec.date || !rec.evaluated_at) {
      warnings.push({ code: "RECORD_MISSING_DATE", message: "Decision record missing date or evaluated_at.", affectedId: i });
    }
  });
  return warnings;
}
