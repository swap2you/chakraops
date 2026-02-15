import { useState } from "react";
import {
  uiApiGet,
  uiEndpoints,
  UiSymbolDiagnosticsResponse,
  UiApiError,
} from "@/data/uiApiClient";
import { Search, AlertCircle, Loader2 } from "lucide-react";

export function SymbolDiagnosticsPage() {
  const [symbol, setSymbol] = useState("SPY");
  const [data, setData] = useState<UiSymbolDiagnosticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDiagnostics = () => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError(null);
    setData(null);
    uiApiGet<UiSymbolDiagnosticsResponse>(uiEndpoints.symbolDiagnostics(sym))
      .then(setData)
      .catch((e) => setError(e instanceof UiApiError ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-xl font-semibold flex items-center gap-2">
        <Search className="h-5 w-5" />
        Symbol Diagnostics
      </h1>

      <div className="flex gap-2">
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && fetchDiagnostics()}
          placeholder="Ticker (e.g. SPY)"
          className="rounded border px-3 py-2 w-32 uppercase"
        />
        <button
          onClick={fetchDiagnostics}
          disabled={loading || !symbol.trim()}
          className="rounded bg-primary text-primary-foreground px-4 py-2 disabled:opacity-50 flex items-center gap-2"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Lookup
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-destructive bg-destructive/10 rounded p-3">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {data && !loading && (
        <div className="border rounded p-4 space-y-3">
          <div>
            <span className="text-sm font-medium text-muted-foreground">primary_reason</span>
            <p className="font-medium">{data.primary_reason ?? "—"}</p>
          </div>
          <div>
            <span className="text-sm font-medium text-muted-foreground">verdict</span>
            <p>{data.verdict ?? "—"}</p>
          </div>
          <div>
            <span className="text-sm font-medium text-muted-foreground">in_universe</span>
            <p>{String(data.in_universe ?? "—")}</p>
          </div>
          {data.gates && data.gates.length > 0 && (
            <div>
              <span className="text-sm font-medium text-muted-foreground">gates</span>
              <ul className="list-disc list-inside text-sm">
                {data.gates.map((g, i) => (
                  <li key={i}>
                    {String((g as Record<string, unknown>).name ?? g.name ?? "—")}: {String((g as Record<string, unknown>).status ?? g.status ?? "—")}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.notes && data.notes.length > 0 && (
            <div>
              <span className="text-sm font-medium text-muted-foreground">notes</span>
              <ul className="list-disc list-inside text-sm">
                {data.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
