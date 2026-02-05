/**
 * Phase 7.2 / 7.3: Top-level decision banner. Answers "What is the system telling me to do today?"
 * When NO_TRADE or RISK_HOLD, shows collapsible "Why no trade" with primary/secondary constraints and evaluation time.
 */
import { useState } from "react";
import type { DailyOverviewView, TradePlanView } from "@/types/views";
import { cn } from "@/lib/utils";

export type BannerState = "READY" | "NO_TRADE" | "RISK_HOLD";

function deriveBannerState(
  overview: DailyOverviewView | null,
  tradePlan: TradePlanView | null
): BannerState {
  if (!overview) return "NO_TRADE";
  const ready =
    overview.trades_ready >= 1 ||
    tradePlan?.execution_status === "READY";
  if (ready) return "READY";
  const regime = (overview.regime ?? "").toUpperCase();
  if (regime === "RISK_OFF") return "RISK_HOLD";
  return "NO_TRADE";
}

const STATE_CONFIG: Record<
  BannerState,
  { headline: string; subline: string; cta: string; className: string }
> = {
  READY: {
    headline: "Trade plan available",
    subline: "Review the trade plan below. No execution until you acknowledge.",
    cta: "Review plan",
    className: "border-l-4 border-emerald-500 bg-emerald-500/10",
  },
  NO_TRADE: {
    headline: "No trade today",
    subline: "No READY setup met criteria. Capital remains protected.",
    cta: "View summary",
    className: "border-l-4 border-slate-500 bg-slate-500/10",
  },
  RISK_HOLD: {
    headline: "Hold — exposure managed",
    subline: "Regime or risk posture indicates holding. Review positions and constraints.",
    cta: "Review positions",
    className: "border-l-4 border-amber-500 bg-amber-500/10",
  },
};

function formatEvalTimestamp(overview: DailyOverviewView): string {
  const ts = overview.links?.latest_decision_ts ?? overview.date;
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? ts : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return ts;
  }
}

export interface DecisionBannerProps {
  overview: DailyOverviewView | null;
  tradePlan: TradePlanView | null;
  onCtaClick?: () => void;
  /** Optional label for context (e.g. "Decision" for historical audit view). */
  label?: string;
}

export function DecisionBanner({
  overview,
  tradePlan,
  onCtaClick,
  label = "Today's decision",
}: DecisionBannerProps) {
  const [whyOpen, setWhyOpen] = useState(false);
  const state = deriveBannerState(overview, tradePlan);
  const config = STATE_CONFIG[state];
  const explanation =
    overview?.why_summary && state !== "READY" ? overview.why_summary : config.subline;
  const showWhyNoTrade = (state === "NO_TRADE" || state === "RISK_HOLD") && overview;
  const topBlockers = overview?.top_blockers ?? [];
  const primary = topBlockers[0];
  const secondary = topBlockers.slice(1, 3);
  const showCta = onCtaClick != null;

  return (
    <section
      className={cn("rounded-lg border border-border p-5", config.className)}
      role="region"
      aria-label={label}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <h2 className="mt-0.5 text-xl font-semibold text-foreground sm:text-2xl">
            {state === "READY" && overview?.trades_ready && overview.trades_ready > 1
              ? `${overview.trades_ready} trade plans available`
              : config.headline}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{explanation}</p>
        </div>
        {showCta && (
          <div className="shrink-0">
            <button
              type="button"
              onClick={onCtaClick}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {config.cta}
            </button>
          </div>
        )}
      </div>

      {showWhyNoTrade && (
        <div className="mt-4 border-t border-border/80 pt-4">
          <button
            type="button"
            onClick={() => setWhyOpen((o) => !o)}
            className="flex w-full items-center justify-between gap-2 rounded-md py-1.5 text-left text-sm font-medium text-muted-foreground hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-expanded={whyOpen}
            aria-controls="why-no-trade-content"
            id="why-no-trade-trigger"
          >
            <span>Why no trade</span>
            <span
              className={cn("shrink-0 transition-transform", whyOpen && "rotate-180")}
              aria-hidden
            >
              ▼
            </span>
          </button>
          <div
            id="why-no-trade-content"
            role="region"
            aria-labelledby="why-no-trade-trigger"
            className={cn("overflow-hidden transition-all", whyOpen ? "visible" : "hidden")}
          >
            <dl className="mt-2 space-y-1.5 text-sm">
              {primary && (
                <>
                  <dt className="text-muted-foreground">Primary constraint</dt>
                  <dd className="font-medium text-foreground">
                    {primary.code}
                    {primary.count > 0 ? ` (${primary.count})` : ""}
                  </dd>
                </>
              )}
              {secondary.length > 0 && (
                <>
                  <dt className="text-muted-foreground">Secondary</dt>
                  <dd className="font-medium text-foreground">
                    {secondary.map((b) => `${b.code}${b.count > 0 ? ` (${b.count})` : ""}`).join(", ")}
                  </dd>
                </>
              )}
              <dt className="text-muted-foreground">Evaluated</dt>
              <dd className="font-medium text-foreground">{formatEvalTimestamp(overview)}</dd>
            </dl>
          </div>
        </div>
      )}
    </section>
  );
}
