/**
 * R27.6: Learn / Operator Guide — wife-friendly, scannable. Safe text only (no FAIL/WARN).
 */
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader } from "@/components/ui";

export function LearnPage() {
  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Learn"
        subtext="Operator guide: daily routine, key terms, and links. No auto-trading; you stay in control."
      />

      <div className="grid gap-6 md:grid-cols-1 max-w-4xl">
        {/* A) Daily routine */}
        <Card data-testid="learn-daily-routine">
          <CardHeader title="Daily routine (10–15 min)" />
          <ol className="list-decimal list-inside space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
            <li>Open <Link to="/today" className="text-emerald-600 hover:underline dark:text-emerald-400">Today</Link>.</li>
            <li>Run evaluation (EOD-biased; check as-of timestamp).</li>
            <li>Handle Action Needed (ENTRY vs CLOSE/ROLL).</li>
            <li>Open <Link to="/ticket" className="text-emerald-600 hover:underline dark:text-emerald-400">Ticket</Link> → Execute manually → Save to <Link to="/journal" className="text-emerald-600 hover:underline dark:text-emerald-400">Journal</Link>.</li>
            <li>Clear inbox (Ack NEW, Archive ACKED).</li>
            <li>Mark EOD checklist done.</li>
          </ol>
        </Card>

        {/* B) What the system does / does not do */}
        <Card data-testid="learn-does-doesnot">
          <CardHeader title="What the system does / does not do" />
          <div className="space-y-3 text-sm text-zinc-700 dark:text-zinc-300">
            <p><strong>Does:</strong> Rules-based suggestions, sizing, guardrails, journaling, reports.</p>
            <p><strong>Does not:</strong> Auto trade, guarantee profit, or do intraday scalping.</p>
          </div>
        </Card>

        {/* C) Key terms */}
        <Card data-testid="learn-key-terms">
          <CardHeader title="Key terms" />
          <ul className="space-y-1.5 text-sm text-zinc-700 dark:text-zinc-300 list-disc list-inside">
            <li><strong>CSP</strong> — Cash-secured put.</li>
            <li><strong>CC</strong> — Covered call.</li>
            <li><strong>DTE</strong> — Days to expiration.</li>
            <li><strong>Mark</strong> — MID / LAST / BID / ASK; mark age = quote freshness.</li>
            <li><strong>Roll window</strong> — When to consider rolling a position.</li>
            <li><strong>Assignment risk</strong> — Short option going ITM near expiry.</li>
            <li><strong>Guardrails</strong> — Cash reserve, cash-secured, symbol cap.</li>
            <li><strong>Sizing constraints</strong> — Limits from account risk and rules (shown with safe labels).</li>
          </ul>
        </Card>

        {/* D) Common mistakes to avoid */}
        <Card data-testid="learn-mistakes">
          <CardHeader title="Common mistakes to avoid" />
          <ul className="space-y-1.5 text-sm text-zinc-700 dark:text-zinc-300 list-disc list-inside">
            <li>Trading during earnings as if it’s normal.</li>
            <li>Ignoring guardrails.</li>
            <li>Not journaling.</li>
            <li>Leaving notifications NEW for days.</li>
          </ul>
        </Card>

        {/* E) Links */}
        <Card data-testid="learn-links">
          <CardHeader title="Links" />
          <div className="space-y-2 text-sm">
            <p className="text-zinc-600 dark:text-zinc-400">Internal:</p>
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              <li><Link to="/today" className="text-emerald-600 hover:underline dark:text-emerald-400">Today</Link></li>
              <li><Link to="/ticket" className="text-emerald-600 hover:underline dark:text-emerald-400">Ticket</Link></li>
              <li><Link to="/journal" className="text-emerald-600 hover:underline dark:text-emerald-400">Journal</Link></li>
              <li><Link to="/reports" className="text-emerald-600 hover:underline dark:text-emerald-400">Reports</Link></li>
              <li><Link to="/system" className="text-emerald-600 hover:underline dark:text-emerald-400">System Diagnostics</Link></li>
            </ul>
            <p className="text-zinc-600 dark:text-zinc-400 mt-3">Add your favorite videos or docs here (bookmark in browser).</p>
          </div>
        </Card>
      </div>
    </div>
  );
}
