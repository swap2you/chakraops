// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R36.1: additive per-recommendation explainability panel. Renders the canonical
// explanation contract (primary/supporting reasons, measured-vs-threshold,
// freshness, near-miss, temporary-vs-safety-critical, expandable calculation
// trace). Advisory-only; shows humanized titles, never raw FAIL_/WARN_ codes.

import { Badge } from "@/components/ui";
import type { MeasuredValue, RecommendationExplanation } from "@/api/types";

function klassVariant(klass?: string): "danger" | "warning" | "neutral" {
  if (klass === "SAFETY_CRITICAL") return "danger";
  if (klass === "TEMPORARY") return "warning";
  return "neutral";
}

function klassLabel(klass?: string): string {
  if (klass === "SAFETY_CRITICAL") return "Safety-critical";
  if (klass === "TEMPORARY") return "Temporary";
  return "Info";
}

function fmtNum(v: number | null | undefined): string {
  if (v == null) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

function thresholdText(t: number | number[] | null | undefined): string {
  if (t == null) return "—";
  if (Array.isArray(t)) return `${fmtNum(t[0])}–${fmtNum(t[1])}`;
  return fmtNum(t);
}

function measuredChipClass(within: boolean | null): string {
  if (within === true) return "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300";
  if (within === false) return "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300";
  return "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400";
}

function MeasuredChip({ mv }: { mv: MeasuredValue }) {
  const unit = mv.unit ? ` ${mv.unit}` : "";
  return (
    <span
      data-testid={`measured-${mv.code}`}
      className={`rounded px-1.5 py-0.5 text-[11px] ${measuredChipClass(mv.within)}`}
      title={`${mv.name} (${mv.comparator} ${thresholdText(mv.threshold)})`}
    >
      {mv.name}: {fmtNum(mv.measured)}{unit} vs {thresholdText(mv.threshold)}{unit}
    </span>
  );
}

export function ExplanationPanel({
  explanation,
}: {
  explanation?: RecommendationExplanation | null;
}) {
  if (!explanation) return null;
  const {
    primary_reason,
    supporting_reasons = [],
    measured_values = [],
    near_miss,
    calculation_trace = [],
    timestamps,
    safety_critical_reasons = [],
  } = explanation;

  return (
    <div
      data-testid="explanation-panel"
      className="mt-2 rounded border border-zinc-200 dark:border-zinc-700 p-2 text-xs"
    >
      {primary_reason && (
        <div className="flex items-start gap-2" data-testid="explanation-primary">
          <Badge variant={klassVariant(primary_reason.klass)}>
            {klassLabel(primary_reason.klass)}
          </Badge>
          <div>
            <div className="font-semibold text-zinc-800 dark:text-zinc-200">
              {primary_reason.title}
            </div>
            <div className="text-zinc-500 dark:text-zinc-400">{primary_reason.explanation}</div>
          </div>
        </div>
      )}

      {supporting_reasons.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1" data-testid="explanation-supporting">
          {supporting_reasons.map((r) => (
            <span
              key={r.code}
              title={r.explanation}
              className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
            >
              {r.title}
            </span>
          ))}
        </div>
      )}

      {measured_values.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1" data-testid="explanation-measured">
          {measured_values.map((mv) => (
            <MeasuredChip key={mv.code} mv={mv} />
          ))}
        </div>
      )}

      {near_miss?.is_near_miss && (
        <div className="mt-1 flex items-center gap-2" data-testid="explanation-near-miss">
          <Badge variant="warning">Near miss</Badge>
          <span className="text-zinc-500 dark:text-zinc-400">{near_miss.note}</span>
        </div>
      )}

      {safety_critical_reasons.length > 0 && (
        <div className="mt-1" data-testid="explanation-safety-critical">
          <Badge variant="danger">Safety-critical: {safety_critical_reasons.length}</Badge>
        </div>
      )}

      {timestamps && (timestamps.price_as_of || timestamps.chain_as_of) && (
        <div className="mt-1 text-[11px] text-zinc-400" data-testid="explanation-freshness">
          Price as of {timestamps.price_as_of ?? "—"} · Chain as of {timestamps.chain_as_of ?? "—"}
        </div>
      )}

      {calculation_trace.length > 0 && (
        <details className="mt-1" data-testid="explanation-calc-trace">
          <summary className="cursor-pointer text-zinc-500 dark:text-zinc-400">
            Calculation trace
          </summary>
          <ul className="mt-1 space-y-0.5">
            {calculation_trace.map((row, i) => (
              <li key={`${row.input}-${i}`} className="text-[11px] text-zinc-500 dark:text-zinc-400">
                <span className="font-medium text-zinc-700 dark:text-zinc-300">{row.input}</span>
                {": "}
                {fmtNum(row.value)}
                {row.unit ? ` ${row.unit}` : ""}
                {row.formula ? ` — ${row.formula}` : ""}
                {row.source ? ` (${row.source}${row.timestamp ? ` @ ${row.timestamp}` : ""})` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
