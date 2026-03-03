import { useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronRight, Copy, Check } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, Button } from "@/components/ui";
import { useTradeTicket, useJournalFromTicket, usePaperExecute } from "@/api/queries";
import { constraintToLabel } from "@/utils/sizingConstraints";

export function TradeTicketPage() {
  const [searchParams] = useSearchParams();
  const symbol = searchParams.get("symbol")?.trim().toUpperCase() ?? "";
  const strategy = (searchParams.get("strategy") ?? "SHARES").trim().toUpperCase();
  const action = (searchParams.get("action") ?? "OPEN").trim().toUpperCase();

  const { data: ticket, isLoading, isError } = useTradeTicket(symbol, strategy, action);
  const saveToJournal = useJournalFromTicket();
  const paperExecute = usePaperExecute();
  const [copiedSection, setCopiedSection] = useState<string | null>(null);
  const [paperMode, setPaperMode] = useState(false);
  const [paperPrice, setPaperPrice] = useState("");
  const [paperFees, setPaperFees] = useState("0");
  const [paperToast, setPaperToast] = useState<string | null>(null);
  const [snapshotOpen, setSnapshotOpen] = useState(true);
  const [sizingOpen, setSizingOpen] = useState(true);
  const [contractOpen, setContractOpen] = useState(true);
  const [stepsOpen, setStepsOpen] = useState(true);
  const [journalOpen, setJournalOpen] = useState(true);

  const copyToClipboard = useCallback(async (text: string, section: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedSection(section);
    setTimeout(() => setCopiedSection(null), 2000);
  }, []);

  const stepsText = (ticket?.execution_steps ?? []).join("\n");
  const journalJson = JSON.stringify(ticket?.journal_draft ?? {}, null, 2);
  const j = ticket?.journal_draft as Record<string, unknown> | undefined;
  const csvLine = j
    ? [j.trade_date, j.symbol, j.strategy, j.action, j.qty, j.price ?? j.premium ?? "", j.contract_key ?? "", j.notes ?? ""].join(",")
    : "";

  const ticketId = searchParams.get("ticket_id")?.trim() ?? "";
  const handleSaveToJournal = useCallback(() => {
    if (!ticket?.journal_draft) return;
    saveToJournal.mutate(ticket.journal_draft as Record<string, unknown>, {
      onSuccess: () => {
        if (ticketId) {
          window.dispatchEvent(new CustomEvent("chakraops-journal-saved", { detail: { ticket_id: ticketId } }));
        }
      },
    });
  }, [ticket?.journal_draft, ticketId, saveToJournal]);

  const handleSimulateFill = useCallback(() => {
    const j = ticket?.journal_draft as Record<string, unknown> | undefined;
    if (!j) return;
    const qty = Number(j.qty) || 0;
    if (qty <= 0) return;
    const strat = (String(j.strategy ?? strategy)).toUpperCase();
    const act = (String(j.action ?? action)).toUpperCase();
    const isOpen = act === "OPEN" || act === "BUY";
    const price = parseFloat(paperPrice);
    const fees = parseFloat(paperFees) || 0;
    const payload = {
      mode: "PAPER" as const,
      symbol: String(j.symbol ?? symbol).toUpperCase(),
      strategy: strat,
      action: isOpen ? "OPEN" : "CLOSE",
      qty,
      fees,
      contract_key: j.contract_key ? String(j.contract_key) : undefined,
      expiry: j.expiry ? String(j.expiry).slice(0, 10) : undefined,
      strike: j.strike != null ? Number(j.strike) : undefined,
      right: j.right ? String(j.right) : undefined,
      notes: j.notes ? String(j.notes).slice(0, 500) : undefined,
    };
    if (strat === "SHARES") {
      (payload as Record<string, unknown>).shares_price = price;
    } else {
      (payload as Record<string, unknown>).premium = price;
    }
    if (!isOpen && (j as { position_id?: string }).position_id) {
      (payload as Record<string, unknown>).position_id = (j as { position_id?: string }).position_id;
    }
    paperExecute.mutate(payload as Parameters<typeof paperExecute.mutate>[0], {
      onSuccess: () => {
        setPaperToast("Paper fill recorded");
        setTimeout(() => setPaperToast(null), 3000);
        if (ticketId) {
          window.dispatchEvent(new CustomEvent("chakraops-journal-saved", { detail: { ticket_id: ticketId } }));
        }
      },
    });
  }, [ticket, symbol, strategy, action, paperPrice, paperFees, ticketId, paperExecute]);

  if (!symbol) {
    return (
      <div className="space-y-4">
        <PageHeader title="Trade Ticket" />
        <Card>
          <CardHeader title="No symbol" description="Open a ticket from Action Needed or Symbol Diagnostics (add ?symbol=...&strategy=...&action=...)." />
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Trade Ticket" />
        <p className="text-sm text-zinc-500">Loading ticket…</p>
      </div>
    );
  }

  if (isError || !ticket) {
    return (
      <div className="space-y-4">
        <PageHeader title="Trade Ticket" />
        <Card>
          <CardHeader title="Error" description="Could not load ticket. Check symbol and try again." />
        </Card>
      </div>
    );
  }

  const header = ticket.snapshot_header as Record<string, unknown>;
  const sizing = ticket.sizing as Record<string, unknown>;
  const contract = ticket.contract_details as Record<string, unknown>;
  const constraints = (sizing.sizing_constraints_hit as string[] | undefined) ?? [];

  return (
    <div className="space-y-3" data-testid="trade-ticket-page">
      <PageHeader title={`Trade Ticket — ${ticket.symbol} ${ticket.strategy} ${ticket.action}`} />
      {ticket.error && (
        <p className="text-sm text-amber-600 dark:text-amber-400">{ticket.error}</p>
      )}

      {/* Snapshot */}
      <details open={snapshotOpen} onToggle={(e) => setSnapshotOpen((e.target as HTMLDetailsElement).open)} className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
          {snapshotOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Snapshot
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-3 py-2 text-sm">
          <p><span className="text-zinc-500">Symbol:</span> {String(header.symbol ?? "")} · <span className="text-zinc-500">Strategy:</span> {String(header.strategy ?? "")} · <span className="text-zinc-500">Action:</span> {String(header.action ?? "")}</p>
          <p><span className="text-zinc-500">Cadence:</span> {String(header.cadence_mode ?? "—")} · <span className="text-zinc-500">As of (ET):</span> {String(header.as_of_et ?? "—")}</p>
          <p><span className="text-zinc-500">Recommended action:</span> {String(header.recommended_action ?? "—")}</p>
        </div>
      </details>

      {/* Sizing */}
      <details open={sizingOpen} onToggle={(e) => setSizingOpen((e.target as HTMLDetailsElement).open)} className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
          {sizingOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Sizing
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-3 py-2 text-sm space-y-1">
          {sizing.recommended_qty != null && <p>Recommended qty (shares): {String(sizing.recommended_qty)}</p>}
          {sizing.recommended_contracts != null && <p>Recommended contracts: {String(sizing.recommended_contracts)}</p>}
          {sizing.recommended_notional_usd != null && <p>Notional: ${Number(sizing.recommended_notional_usd).toLocaleString()}</p>}
          {constraints.length > 0 && <p>Constraints: {constraints.map((c) => constraintToLabel(c)).join(", ")}</p>}
          {sizing.cash_secured_available_usd != null && <p>Cash-secured available: ${Number(sizing.cash_secured_available_usd).toLocaleString()}</p>}
          {sizing.csp_risk_proxy_move_pct != null && <p>Risk proxy move: {Number(sizing.csp_risk_proxy_move_pct)}%</p>}
          {sizing.csp_risk_proxy_loss_per_contract_usd != null && <p>Risk proxy loss (per contract): ${Number(sizing.csp_risk_proxy_loss_per_contract_usd).toLocaleString()}</p>}
          {sizing.csp_risk_proxy_cap_contracts != null && <p>Risk proxy cap: {String(sizing.csp_risk_proxy_cap_contracts)} contracts{sizing.csp_risk_proxy_enforced ? " (enforced)" : ""}</p>}
        </div>
      </details>

      {/* Contract (options) */}
      {(ticket.strategy === "CSP" || ticket.strategy === "CC") && (
        <details open={contractOpen} onToggle={(e) => setContractOpen((e.target as HTMLDetailsElement).open)} className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
          <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
            {contractOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            Contract
          </summary>
          <div className="border-t border-zinc-200 dark:border-zinc-700 px-3 py-2 text-sm space-y-1">
            {contract.expiry != null && <p>Expiry: {String(contract.expiry)}</p>}
            {contract.strike != null && <p>Strike: ${Number(contract.strike)}</p>}
            {contract.right != null && <p>Right: {String(contract.right)}</p>}
            {contract.dte != null && <p>DTE: {String(contract.dte)}</p>}
            {contract.mark_value != null && <p>Mark: {Number(contract.mark_value)}{contract.mark_source ? ` (${contract.mark_source}${contract.mark_age_sec != null ? `, ${contract.mark_age_sec}s` : ""})` : ""}</p>}
            {contract.premium != null && <p>Premium: ${Number(contract.premium)}</p>}
            {contract.pct_max_profit != null && <p>Max profit %: {Number(contract.pct_max_profit)}</p>}
          </div>
        </details>
      )}

      {/* Execution steps */}
      <details open={stepsOpen} onToggle={(e) => setStepsOpen((e.target as HTMLDetailsElement).open)} className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
          {stepsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Execution steps
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-3 py-2 text-sm flex items-start justify-between gap-2">
          <pre className="whitespace-pre-wrap text-zinc-700 dark:text-zinc-300 flex-1">{stepsText}</pre>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => copyToClipboard(stepsText, "steps")}
            data-testid="ticket-copy-steps"
          >
            {copiedSection === "steps" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </Button>
        </div>
      </details>

      {/* Journal draft */}
      <details open={journalOpen} onToggle={(e) => setJournalOpen((e.target as HTMLDetailsElement).open)} className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
          {journalOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Journal draft
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-3 py-2 text-sm space-y-2">
          <pre className="text-xs overflow-x-auto text-zinc-600 dark:text-zinc-400">{journalJson}</pre>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="primary" onClick={handleSaveToJournal} disabled={saveToJournal.isPending} data-testid="ticket-save-journal">
              {saveToJournal.isPending ? "Saving…" : "Save to Journal"}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => copyToClipboard(journalJson, "json")} data-testid="ticket-copy-json">
              {copiedSection === "json" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} Copy JSON
            </Button>
            <Button size="sm" variant="secondary" onClick={() => copyToClipboard(csvLine, "csv")} data-testid="ticket-copy-csv">
              {copiedSection === "csv" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} Copy CSV line
            </Button>
          </div>
        </div>
      </details>

      {/* R27.0: Paper execute */}
      <details className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60" data-testid="ticket-paper-section">
        <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
          Paper execute
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-3 py-2 text-sm space-y-2">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={paperMode}
              onChange={(e) => setPaperMode(e.target.checked)}
              data-testid="ticket-paper-toggle"
            />
            Simulate fill (paper trade)
          </label>
          {paperMode && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-zinc-600 dark:text-zinc-400">
                  {strategy === "SHARES" ? "Price" : "Premium"}:
                </label>
                <input
                  type="number"
                  step="any"
                  value={paperPrice}
                  onChange={(e) => setPaperPrice(e.target.value)}
                  placeholder={strategy === "SHARES" ? "e.g. 450" : "e.g. 2.50"}
                  className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1 w-24"
                  data-testid="ticket-paper-price"
                />
                <label className="text-zinc-600 dark:text-zinc-400">Fees:</label>
                <input
                  type="number"
                  step="any"
                  value={paperFees}
                  onChange={(e) => setPaperFees(e.target.value)}
                  className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1 w-20"
                  data-testid="ticket-paper-fees"
                />
              </div>
              <Button
                size="sm"
                variant="primary"
                onClick={handleSimulateFill}
                disabled={paperExecute.isPending || !paperPrice.trim()}
                data-testid="ticket-paper-simulate"
              >
                {paperExecute.isPending ? "Saving…" : "Simulate Fill"}
              </Button>
              {paperToast && <p className="text-emerald-600 dark:text-emerald-400" data-testid="ticket-paper-toast">{paperToast}</p>}
            </>
          )}
        </div>
      </details>
    </div>
  );
}
