import { useEffect, useState } from "react";
import { uiApiGet, uiEndpoints, UiApiError } from "@/data/uiApiClient";
import { FileJson, AlertCircle, Loader2 } from "lucide-react";

export function DecisionPage() {
  const [mode, setMode] = useState<"LIVE" | "MOCK">("LIVE");
  const [files, setFiles] = useState<{ name: string; mtime_iso: string; size_bytes: number }[]>([]);
  const [latest, setLatest] = useState<Record<string, unknown> | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    uiApiGet<{ mode: string; dir: string; files: { name: string; mtime_iso: string; size_bytes: number }[] }>(
      uiEndpoints.decisionFiles(mode)
    )
      .then((r) => {
        if (!cancelled) {
          setFiles(r.files);
          if (r.files.length > 0 && !selectedFile) {
            const fn = r.files.find((f) => f.name === "decision_latest.json")?.name ?? r.files[0].name;
            setSelectedFile(fn);
          }
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof UiApiError ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [mode]);

  useEffect(() => {
    if (!selectedFile) {
      setLatest(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const path =
      selectedFile === "decision_latest.json"
        ? uiEndpoints.decisionLatest(mode)
        : uiEndpoints.decisionFile(selectedFile, mode);
    uiApiGet<Record<string, unknown>>(path)
      .then((r) => {
        if (!cancelled) setLatest(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof UiApiError ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [mode, selectedFile]);

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Decision</h1>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as "LIVE" | "MOCK")}
          className="rounded border px-2 py-1 text-sm"
        >
          <option value="LIVE">LIVE</option>
          <option value="MOCK">MOCK</option>
        </select>
      </div>

      <div className="flex items-center gap-4 border rounded p-2 bg-muted/30">
        <FileJson className="h-5 w-5" />
        <span className="text-sm font-medium">Artifact:</span>
        <select
          value={selectedFile ?? ""}
          onChange={(e) => setSelectedFile(e.target.value || null)}
          className="flex-1 rounded border px-2 py-1 text-sm max-w-xs"
        >
          <option value="">—</option>
          {files.map((f) => (
            <option key={f.name} value={f.name}>
              {f.name} ({new Date(f.mtime_iso).toLocaleString()})
            </option>
          ))}
        </select>
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

      {latest && !loading && (
        <div className="border rounded p-4">
          <pre className="text-xs overflow-auto max-h-[60vh] whitespace-pre-wrap break-words">
            {JSON.stringify(latest, null, 2)}
          </pre>
        </div>
      )}

      {!latest && !loading && !error && (
        <p className="text-muted-foreground text-sm">No artifact selected or no files available.</p>
      )}
    </div>
  );
}
