import { useEffect, useState } from "react";
import { uiApiGet, uiEndpoints, UiUniverseResponse, UiApiError } from "@/data/uiApiClient";
import { Globe, AlertCircle, Loader2 } from "lucide-react";

export function UniversePage() {
  const [data, setData] = useState<UiUniverseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    uiApiGet<UiUniverseResponse>(uiEndpoints.universe())
      .then((r) => { if (!cancelled) setData(r); })
      .catch((e) => {
        if (!cancelled) setError(e instanceof UiApiError ? e.message : String(e));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Globe className="h-5 w-5" />
          Universe
        </h1>
        {data && (
          <span className="text-sm text-muted-foreground">
            {data.source} · Updated {data.updated_at ? new Date(data.updated_at).toLocaleString() : "—"}
          </span>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 text-destructive bg-destructive/10 rounded p-3">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Loading…</span>
        </div>
      )}

      {data && !loading && (
        <div className="border rounded overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 border-b">
                <th className="text-left p-2 font-medium">Symbol</th>
                <th className="text-left p-2 font-medium">Price</th>
                <th className="text-left p-2 font-medium">Expiration</th>
              </tr>
            </thead>
            <tbody>
              {(data.symbols ?? []).map((s, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="p-2">{String((s as Record<string, unknown>).symbol ?? "—")}</td>
                  <td className="p-2">{String((s as Record<string, unknown>).price ?? "—")}</td>
                  <td className="p-2">{String((s as Record<string, unknown>).expiration ?? "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!data.symbols || data.symbols.length === 0) && (
            <p className="p-4 text-muted-foreground text-center">No symbols loaded.</p>
          )}
        </div>
      )}
    </div>
  );
}
