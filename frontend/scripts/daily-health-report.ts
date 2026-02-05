/**
 * Phase 9: Daily summary report — reads health artifacts for a day, produces markdown + JSON.
 * Run from frontend/: npx tsx scripts/daily-health-report.ts [YYYY-MM-DD]
 * Default date: today (UTC). Artifacts dir: ARTIFACTS_DIR or ./artifacts (relative to cwd). Windows-safe paths.
 */
import * as fs from "node:fs";
import * as path from "node:path";

const ARTIFACTS_DIR = process.env.ARTIFACTS_DIR ?? path.join(process.cwd(), "artifacts");
const REPORTS_DIR = process.env.REPORTS_DAILY_DIR ?? path.join(process.cwd(), "reports", "daily");

interface EndpointResult {
  path: string;
  status: number;
  ok: boolean;
  parseable: boolean;
  schemaValid: boolean;
  warnings: string[];
  durationMs: number;
}

interface HealthReport {
  timestamp: string;
  marketPhase: string;
  endpointStatus: Record<string, EndpointResult>;
  validationWarnings: string[];
  executionDurationMs: number;
  success: boolean;
}

interface DailySummary {
  date: string;
  reports: HealthReport[];
  apiHealthTimeline: { phase: string; timestamp: string; success: boolean }[];
  evaluationTimestamps: string[];
  alertsCountPerPhase: Record<string, number>;
  decisionsCountPerPhase: Record<string, number>;
  warnings: string[];
  anomalies: string[];
}

function parseReportPath(filePath: string): { date: string; time: string } | null {
  const name = path.basename(filePath, path.extname(filePath));
  const match = name.match(/market_health_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})/);
  return match ? { date: match[1], time: match[2] } : null;
}

function readReportsForDate(artifactsDir: string, date: string): HealthReport[] {
  const reports: HealthReport[] = [];
  if (!fs.existsSync(artifactsDir)) return reports;
  const files = fs.readdirSync(artifactsDir);
  for (const f of files) {
    if (!f.endsWith(".json")) continue;
    const parsed = parseReportPath(f);
    if (!parsed || parsed.date !== date) continue;
    try {
      const raw = fs.readFileSync(path.join(artifactsDir, f), "utf8");
      reports.push(JSON.parse(raw) as HealthReport);
    } catch {
      /* skip invalid */
    }
  }
  reports.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  return reports;
}

function buildSummary(date: string, reports: HealthReport[]): DailySummary {
  const apiHealthTimeline = reports.map((r) => ({
    phase: r.marketPhase,
    timestamp: r.timestamp,
    success: r.success,
  }));
  const evaluationTimestamps: string[] = [];
  const alertsCountPerPhase: Record<string, number> = {};
  const decisionsCountPerPhase: Record<string, number> = {};
  const warnings: string[] = [];
  const anomalies: string[] = [];

  for (const r of reports) {
    alertsCountPerPhase[r.marketPhase] = (alertsCountPerPhase[r.marketPhase] ?? 0) + 0;
    decisionsCountPerPhase[r.marketPhase] = (decisionsCountPerPhase[r.marketPhase] ?? 0) + 0;
    if (!r.success) anomalies.push(`${r.timestamp} (${r.marketPhase}): failed`);
    warnings.push(...r.validationWarnings);
  }

  return {
    date,
    reports,
    apiHealthTimeline,
    evaluationTimestamps: [...new Set(evaluationTimestamps)].sort(),
    alertsCountPerPhase,
    decisionsCountPerPhase,
    warnings: [...new Set(warnings)],
    anomalies,
  };
}

function markdownReport(summary: DailySummary): string {
  const lines: string[] = [
    `# Daily Health Report — ${summary.date}`,
    "",
    "## API health timeline",
    "| Phase | Timestamp | Success |",
    "|-------|-----------|---------|",
  ];
  for (const t of summary.apiHealthTimeline) {
    lines.push(`| ${t.phase} | ${t.timestamp} | ${t.success ? "Yes" : "No"} |`);
  }
  lines.push("", "## Evaluation timestamps observed", "");
  for (const ts of summary.evaluationTimestamps) {
    lines.push(`- ${ts}`);
  }
  if (summary.evaluationTimestamps.length === 0) lines.push("- (none)");
  lines.push("", "## Alerts count per phase", "");
  for (const [phase, count] of Object.entries(summary.alertsCountPerPhase)) {
    lines.push(`- ${phase}: ${count}`);
  }
  lines.push("", "## Decisions count per phase", "");
  for (const [phase, count] of Object.entries(summary.decisionsCountPerPhase)) {
    lines.push(`- ${phase}: ${count}`);
  }
  lines.push("", "## Warnings", "");
  for (const w of summary.warnings) {
    lines.push(`- ${w}`);
  }
  if (summary.warnings.length === 0) lines.push("- (none)");
  lines.push("", "## Anomalies", "");
  for (const a of summary.anomalies) {
    lines.push(`- ${a}`);
  }
  if (summary.anomalies.length === 0) lines.push("- (none)");
  return lines.join("\n");
}

function main(): void {
  const dateArg = process.argv[2];
  const date = dateArg ?? new Date().toISOString().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    console.error("Usage: daily-health-report.ts [YYYY-MM-DD]");
    process.exit(1);
  }

  const artifactsDir = path.isAbsolute(ARTIFACTS_DIR) ? ARTIFACTS_DIR : path.join(process.cwd(), ARTIFACTS_DIR);
  const reportsDir = path.isAbsolute(REPORTS_DIR) ? REPORTS_DIR : path.join(process.cwd(), REPORTS_DIR);

  const reports = readReportsForDate(artifactsDir, date);
  if (reports.length === 0) {
    console.log(`No health artifacts found for ${date} in ${artifactsDir}`);
    process.exit(0);
  }

  const summary = buildSummary(date, reports);
  const md = markdownReport(summary);
  const fullJsonOut = JSON.stringify(summary, null, 2);

  fs.mkdirSync(reportsDir, { recursive: true });
  const mdPath = path.join(reportsDir, `${date}.md`);
  const jsonPath = path.join(reportsDir, `${date}.json`);
  fs.writeFileSync(mdPath, md, "utf8");
  fs.writeFileSync(jsonPath, fullJsonOut, "utf8");
  console.log(`Report written: ${mdPath}, ${jsonPath}`);
}

main();
