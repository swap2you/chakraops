import { useState } from "react";
import { useSymbolDiagnostics } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";

export function SymbolDiagnosticsPage() {
  const [symbol, setSymbol] = useState("SPY");
  const { data, isLoading, isError, refetch } = useSymbolDiagnostics(symbol);

  return (
    <div>
      <PageHeader title="Symbol Diagnostics" />
      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && refetch()}
          placeholder="Ticker (e.g. SPY)"
          className="w-32 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-zinc-200 uppercase"
        />
        <button
          onClick={() => refetch()}
          disabled={!symbol.trim() || isLoading}
          className="rounded border border-zinc-600 bg-zinc-800 px-3 py-1 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
        >
          Lookup
        </button>
      </div>

      {isLoading && <p className="text-zinc-400">Loading…</p>}

      {isError && <p className="text-red-400">Failed to load diagnostics.</p>}

      {data && !isLoading && (
        <div className="space-y-4">
          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-400">Overview</h2>
            <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-zinc-500">symbol</span>
                  <p className="font-mono">{data.symbol}</p>
                </div>
                <div>
                  <span className="text-zinc-500">verdict</span>
                  <p><StatusBadge status={data.verdict ?? "—"} /></p>
                </div>
                <div>
                  <span className="text-zinc-500">primary_reason</span>
                  <p className="text-zinc-300">{data.primary_reason ?? "—"}</p>
                </div>
                <div>
                  <span className="text-zinc-500">in_universe</span>
                  <p>{String(data.in_universe)}</p>
                </div>
              </div>
            </div>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-400">Stage Breakdown (Gates)</h2>
            <div className="rounded border border-zinc-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/50">
                    <th className="px-3 py-2 text-left text-zinc-400">Name</th>
                    <th className="px-3 py-2 text-left text-zinc-400">Status</th>
                    <th className="px-3 py-2 text-left text-zinc-400">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {data.gates?.map((g, i) => (
                    <tr key={i} className="border-b border-zinc-800/50 last:border-0">
                      <td className="px-3 py-2">{g.name}</td>
                      <td className="px-3 py-2">
                        <StatusBadge status={g.status} />
                      </td>
                      <td className="px-3 py-2 text-zinc-400">{g.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(!data.gates?.length) && <p className="p-4 text-zinc-500">No gates.</p>}
            </div>
          </section>

          {data.symbol_eligibility && (
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-400">Symbol Eligibility</h2>
              <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-zinc-500">status</span>
                    <p><StatusBadge status={data.symbol_eligibility.status} /></p>
                  </div>
                  <div>
                    <span className="text-zinc-500">required_data_missing</span>
                    <p className="font-mono text-zinc-300">
                      {data.symbol_eligibility.required_data_missing?.join(", ") ?? "—"}
                    </p>
                  </div>
                  <div>
                    <span className="text-zinc-500">required_data_stale</span>
                    <p className="font-mono text-zinc-300">
                      {data.symbol_eligibility.required_data_stale?.join(", ") ?? "—"}
                    </p>
                  </div>
                  <div>
                    <span className="text-zinc-500">reasons</span>
                    <p className="text-zinc-400">
                      {data.symbol_eligibility.reasons?.join("; ") ?? "—"}
                    </p>
                  </div>
                </div>
              </div>
            </section>
          )}

          {data.liquidity && (
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-400">Liquidity</h2>
              <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div>
                    <span className="text-zinc-500">stock_liquidity_ok</span>
                    <p>
                      {data.liquidity.stock_liquidity_ok == null
                        ? "—"
                        : data.liquidity.stock_liquidity_ok
                          ? "OK"
                          : "FAIL"}
                    </p>
                  </div>
                  <div>
                    <span className="text-zinc-500">option_liquidity_ok</span>
                    <p>
                      {data.liquidity.option_liquidity_ok == null
                        ? "—"
                        : data.liquidity.option_liquidity_ok
                          ? "OK"
                          : "FAIL"}
                    </p>
                  </div>
                  <div>
                    <span className="text-zinc-500">reason</span>
                    <p className="text-zinc-400">{data.liquidity.reason ?? "—"}</p>
                  </div>
                </div>
              </div>
            </section>
          )}

          {data.blockers?.length ? (
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-400">Blockers</h2>
              <ul className="list-disc list-inside space-y-1 rounded border border-zinc-800 bg-zinc-900/50 p-3 text-sm text-zinc-300">
                {data.blockers.map((b, i) => (
                  <li key={i}>
                    [{b.code}] {b.message}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {data.notes?.length ? (
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-400">Notes</h2>
              <ul className="list-disc list-inside space-y-1 text-sm text-zinc-500">
                {data.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      )}

      {!data && !isLoading && !isError && (
        <p className="text-zinc-500">Enter a symbol and click Lookup.</p>
      )}
    </div>
  );
}
