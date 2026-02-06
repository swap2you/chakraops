/**
 * Pipeline Details — implementation-truthful interactive view of the evaluation pipeline.
 * Renders the same 7 stages as Strategy; each stage expands to show Purpose, Inputs (with source),
 * Outputs, Failure modes (with reason codes), and Where to verify.
 * Content aligns with chakraops/docs/EVALUATION_PIPELINE.md and DATA_DICTIONARY.md.
 */
import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Globe,
  Activity,
  BarChart2,
  Target,
  Layers,
  Wrench,
  Gauge,
  ChevronDown,
  FileText,
  ExternalLink,
} from "lucide-react";
import { Link } from "react-router-dom";
import { PIPELINE_DETAILS, type PipelineStageDetail } from "../data/pipelineDetails";

const STAGE_ICONS = [Globe, Activity, BarChart2, Target, Layers, Wrench, Gauge] as const;
const STAGE_COLORS = [
  "from-blue-500 to-cyan-500",
  "from-violet-500 to-purple-500",
  "from-emerald-500 to-green-500",
  "from-orange-500 to-amber-500",
  "from-pink-500 to-rose-500",
  "from-sky-500 to-blue-500",
  "from-indigo-500 to-violet-500",
] as const;

function GlassCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl border border-white/10 bg-gradient-to-br from-white/5 to-white/[0.02] backdrop-blur-sm ${className}`}
    >
      {children}
    </div>
  );
}

export function PipelinePage() {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="min-h-screen">
      <div className="relative overflow-hidden border-b border-border bg-gradient-to-b from-primary/5 to-transparent px-4 py-10 sm:px-6 lg:px-8">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-primary/10 via-transparent to-transparent" />
        <div className="relative mx-auto max-w-7xl">
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Pipeline Details</h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Implementation-truthful reference for each evaluation stage: inputs (with source), outputs,
              failure modes with reason codes, and where to verify in run JSON and API.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Link
                to="/strategy"
                className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
              >
                <FileText className="h-4 w-4" /> Strategy overview
              </Link>
              <span className="text-muted-foreground">·</span>
              <span className="text-xs text-muted-foreground">
                Backend docs: <code className="rounded bg-muted px-1">chakraops/docs/EVALUATION_PIPELINE.md</code>,{" "}
                <code className="rounded bg-muted px-1">DATA_DICTIONARY.md</code>
              </span>
            </div>
          </motion.div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl space-y-4 px-4 py-8 sm:px-6 lg:px-8">
        {PIPELINE_DETAILS.map((stage, idx) => (
          <StageCard
            key={stage.id}
            stage={stage}
            icon={STAGE_ICONS[idx]}
            color={STAGE_COLORS[idx]}
            isExpanded={expandedId === stage.id}
            onToggle={() => setExpandedId((prev) => (prev === stage.id ? null : stage.id))}
          />
        ))}
      </div>
    </div>
  );
}

function StageCard({
  stage,
  icon: Icon,
  color,
  isExpanded,
  onToggle,
}: {
  stage: PipelineStageDetail;
  icon: React.ElementType;
  color: string;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <GlassCard className="overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-4 p-5 text-left transition-colors hover:bg-white/[0.03]"
      >
        <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${color}`}>
          <Icon className="h-6 w-6 text-white" />
        </div>
        <div className="min-w-0 flex-1">
          <span className="text-xs font-medium text-muted-foreground">Stage {stage.stageNumber}</span>
          <h3 className="font-semibold text-foreground">{stage.title}</h3>
        </div>
        <ChevronDown
          className={`h-5 w-5 shrink-0 text-muted-foreground transition-transform ${isExpanded ? "rotate-180" : ""}`}
        />
      </button>
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="border-t border-white/10"
          >
            <div className="space-y-6 p-5 pt-4">
              <Section title="Purpose" icon={FileText}>
                <p className="text-sm leading-relaxed text-muted-foreground">{stage.purpose}</p>
              </Section>
              <Section title="Inputs (source)" icon={FileText}>
                <ul className="space-y-2">
                  {stage.inputs.map((inp, i) => (
                    <li key={i} className="flex flex-col gap-0.5 text-sm">
                      <span className="font-medium text-foreground">{inp.name}</span>
                      <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{inp.source}</code>
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Outputs" icon={FileText}>
                <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                  {stage.outputs.map((out, i) => (
                    <li key={i}>{out}</li>
                  ))}
                </ul>
              </Section>
              <Section title="Failure modes (reason codes)" icon={FileText}>
                <ul className="space-y-2">
                  {stage.failureModes.map((fm, i) => (
                    <li key={i} className="flex flex-wrap items-baseline gap-2 text-sm">
                      <span className="font-medium text-foreground">{fm.condition}</span>
                      <span className="text-muted-foreground">→</span>
                      <span className="text-muted-foreground">{fm.result}</span>
                      {fm.code && (
                        <code className="rounded bg-amber-500/15 px-1.5 py-0.5 text-xs text-amber-600 dark:text-amber-400">
                          {fm.code}
                        </code>
                      )}
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Where to verify" icon={ExternalLink}>
                <ul className="space-y-1.5">
                  {stage.whereToVerify.map((w, i) => (
                    <li key={i} className="flex items-center gap-2 text-sm">
                      <span className="font-medium text-foreground">{w.label}:</span>
                      <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{w.path}</code>
                    </li>
                  ))}
                </ul>
              </Section>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlassCard>
  );
}

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h4 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        <Icon className="h-3.5 w-3.5" /> {title}
      </h4>
      {children}
    </div>
  );
}
