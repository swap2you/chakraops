# ChakraOps Frontend–Backend Wiring Audit

**Generated:** Comparison of `frontend/src/api/types.ts`, `frontend/src/api/queries.ts`, `frontend/src/api/client.ts`, and UI pages against `UI_CONTRACT_REPORT.md` and backend `app/api/ui_routes.py`.

---

## 1. Endpoint-by-Endpoint Comparison

### `/api/ui/decision/files` (ArtifactListResponse)

| Contract Field   | types.ts        | Backend Provides | Match |
|------------------|-----------------|------------------|-------|
| mode             | ✅ `mode`       | ✅               | OK    |
| dir              | ✅ `dir`        | ✅               | OK    |
| files[]          | ✅ `files`      | ✅               | OK    |
| files[].name     | ✅              | ✅               | OK    |
| files[].mtime_iso| ✅              | ✅               | OK    |
| files[].size_bytes| ✅             | ✅               | OK    |

**Verdict:** Match.

---

### `/api/ui/decision/latest` and `/api/ui/decision/file/{filename}` (DecisionResponse)

| Contract Field                         | types.ts     | Backend Provides | Match |
|----------------------------------------|-------------|------------------|-------|
| decision_snapshot.stats.*              | ✅          | ✅               | OK    |
| decision_snapshot.candidates[]         | ✅          | ✅               | OK    |
| decision_snapshot.selected_signals[]   | ✅          | ✅               | OK    |
| decision_snapshot.exclusions[]         | ✅          | ✅               | OK    |
| decision_snapshot.data_source          | ✅          | ✅               | OK    |
| decision_snapshot.as_of                | ✅          | ✅               | OK    |
| decision_snapshot.pipeline_timestamp   | ✅          | ✅               | OK    |
| decision_snapshot.trade_proposal       | ✅          | ✅               | OK    |
| decision_snapshot.why_no_trade.summary | ✅          | ✅               | OK    |
| execution_gate_result.allowed          | ✅          | ✅               | OK    |
| execution_gate_result.reasons[]        | ✅          | ✅               | OK    |
| execution_gate.*                       | ✅          | ✅               | OK    |
| execution_plan.allowed                 | ✅          | ✅               | OK    |
| execution_plan.blocked_reason          | ✅          | ✅               | OK    |
| execution_plan.orders[]                | ✅          | ✅               | OK    |
| dry_run_result.allowed                 | ✅          | ✅               | OK    |
| metadata.data_source                   | ✅          | ✅               | OK    |
| metadata.pipeline_timestamp            | ✅          | ✅               | OK    |

**Verdict:** Match.

---

### `/api/ui/universe` (UniverseResponse)

| Contract Field    | types.ts       | Backend Provides | Match |
|-------------------|----------------|------------------|-------|
| source            | ✅             | ✅               | OK    |
| updated_at        | ✅             | ✅               | OK    |
| as_of             | ✅             | ✅               | OK    |
| symbols[]         | ✅             | ✅               | OK    |
| symbols[].symbol  | ✅             | ✅               | OK    |
| symbols[].price   | ✅ (optional)  | ✅ (from source) | OK    |
| symbols[].expiration | ✅ (optional) | ✅ (from normalizer) | OK |
| symbols[].final_verdict | ✅ (optional) | ✅ (from normalizer) | OK |
| symbols[].score   | ✅ (optional)  | ✅ (from normalizer) | OK |
| symbols[].band    | ✅ (optional)  | ⚠️ From artifact only | Optional |
| symbols[].primary_reason | ✅ (optional) | ⚠️ From artifact only | Optional |
| error             | ✅ (optional)  | ✅               | OK    |

**Verdict:** Match. `band` and `primary_reason` are optional; backend supplies them when using evaluation artifacts.

---

### `/api/ui/symbol-diagnostics` (SymbolDiagnosticsResponseExtended)

| Contract Field   | types.ts     | Backend Provides | Match |
|------------------|-------------|------------------|-------|
| symbol           | ✅          | ✅               | OK    |
| primary_reason   | ✅          | ✅               | OK    |
| verdict          | ✅          | ✅               | OK    |
| in_universe      | ✅          | ✅               | OK    |
| stock            | ✅          | ✅               | OK    |
| gates[]          | ✅          | ✅               | OK    |
| blockers[]       | ✅          | ✅               | OK    |
| notes[]          | ✅          | ✅               | OK    |
| symbol_eligibility | ✅ (extended) | ✅ (ui_routes) | OK |
| symbol_eligibility.status | ✅ | ✅ | OK |
| symbol_eligibility.required_data_missing | ✅ | ✅ | OK |
| symbol_eligibility.required_data_stale  | ✅ | ✅ | OK |
| symbol_eligibility.reasons | ✅ | ✅ | OK |
| liquidity        | ✅ (extended) | ✅ (ui_routes) | OK |
| liquidity.stock_liquidity_ok | ✅ | ✅ | OK |
| liquidity.option_liquidity_ok | ✅ | ✅ | OK |
| liquidity.reason | ✅ | ✅ | OK |

**Verdict:** Match.

---

## 2. Page Field Access vs Contract

### DashboardPage — Fields Accessed

| Field Path | types.ts | Contract | Notes |
|------------|----------|----------|-------|
| decision?.decision_snapshot | ✅ | ✅ | |
| snapshot?.stats | ✅ | ✅ | |
| stats?.symbols_evaluated | ✅ | ✅ | |
| stats?.total_candidates | ✅ | ✅ | |
| stats?.selected_count | ✅ | ✅ | |
| decision?.execution_plan | ✅ | ✅ | |
| executionPlan?.allowed | ✅ | ✅ | |
| executionPlan?.blocked_reason | ✅ | ✅ | |
| executionPlan?.orders?.length | ✅ | ✅ | |
| decision?.execution_gate | ✅ | ✅ | |
| executionGate?.allowed | ✅ | ✅ | |
| executionGate?.reasons | ✅ | ✅ | |
| snapshot?.selected_signals | ✅ | ✅ | |
| s.symbol | ✅ | ✅ | |
| s.verdict | ✅ | ✅ | |
| s.candidate?.strategy | ✅ | ✅ | |
| s.candidate?.strike | ✅ | ✅ | |
| s.candidate?.delta | ✅ | ✅ | |
| decision?.metadata | ✅ | ✅ | |
| metadata?.data_source | ✅ | ✅ | |
| metadata?.pipeline_timestamp | ✅ | ✅ | |
| files?.files | ✅ | ✅ | |
| f.name | ✅ | ✅ | |

All accessed fields exist in types and contract.

---

### UniversePage — Fields Accessed

| Field Path | types.ts | Contract | Notes |
|------------|----------|----------|-------|
| data?.symbols | ✅ | ✅ | |
| data?.source | ✅ | ✅ | |
| data?.updated_at | ✅ | ✅ | |
| row.symbol | ✅ | ✅ | |
| row.final_verdict | ✅ | ✅ | |
| row.verdict | ✅ | ✅ | |
| row.score | ✅ | ✅ | |
| row.band | ✅ | Optional | Backend only when artifact source |
| row.primary_reason | ✅ | Optional | Backend only when artifact source |
| row.price | ✅ | ✅ | |
| row.expiration | ✅ | ✅ | |

All accessed fields exist. `band` and `primary_reason` are optional; UI handles undefined with fallback "—".

---

### SymbolDiagnosticsPage — Fields Accessed

| Field Path | types.ts | Contract | Notes |
|------------|----------|----------|-------|
| data.symbol | ✅ | ✅ | |
| data.verdict | ✅ | ✅ | |
| data.primary_reason | ✅ | ✅ | |
| data.in_universe | ✅ | ✅ | |
| data.gates | ✅ | ✅ | |
| g.name | ✅ | ✅ | |
| g.status | ✅ | ✅ | |
| g.reason | ✅ | ✅ | |
| data.symbol_eligibility | ✅ | ✅ (extended) | |
| data.symbol_eligibility.status | ✅ | ✅ | |
| data.symbol_eligibility.required_data_missing | ✅ | ✅ | |
| data.symbol_eligibility.required_data_stale | ✅ | ✅ | |
| data.symbol_eligibility.reasons | ✅ | ✅ | |
| data.liquidity | ✅ | ✅ (extended) | |
| data.liquidity.stock_liquidity_ok | ✅ | ✅ | |
| data.liquidity.option_liquidity_ok | ✅ | ✅ | |
| data.liquidity.reason | ✅ | ✅ | |
| data.blockers | ✅ | ✅ | |
| b.code | ✅ | ✅ | |
| b.message | ✅ | ✅ | |
| data.notes | ✅ | ✅ | |

All accessed fields exist.

---

## 3. MISSING_FIELDS (Frontend Expects, Backend May Not Provide)

| Field | Page | Risk | Notes |
|-------|------|------|-------|
| symbols[].band | UniversePage | LOW | From evaluation artifact only; canonical snapshot may omit. UI uses "—" when undefined. |
| symbols[].primary_reason | UniversePage | LOW | Same as band. |
| symbol_eligibility | SymbolDiagnosticsPage | LOW | Wrapped in `data.symbol_eligibility &&`; no crash if absent. |
| liquidity | SymbolDiagnosticsPage | LOW | Wrapped in `data.liquidity &&`; no crash if absent. |

**Conclusion:** None of these cause runtime errors; missing values are handled.

---

## 4. UNUSED_FIELDS (Backend Provides, UI Never Renders)

| Field | Endpoint | Notes |
|-------|----------|-------|
| decision_snapshot.candidates | Decision | Listed in contract; Dashboard shows selected_signals only. |
| decision_snapshot.exclusions | Decision | Not shown. |
| decision_snapshot.data_source | Decision | Not shown (metadata.data_source is). |
| decision_snapshot.as_of | Decision | Not shown. |
| decision_snapshot.pipeline_timestamp | Decision | Not shown (metadata.pipeline_timestamp is). |
| decision_snapshot.trade_proposal | Decision | Not shown. |
| decision_snapshot.why_no_trade.summary | Decision | Not shown. |
| execution_gate_result | Decision | Shown as execution_gate (same shape). |
| dry_run_result | Decision | Not shown. |
| data.as_of | Universe | Not shown (updated_at is). |
| data.error | Universe | Not shown. |
| stock.* | SymbolDiagnostics | Not shown (price, bid, ask, etc.). |
| blockers[].severity | SymbolDiagnostics | Not shown. |
| blockers[].impact | SymbolDiagnostics | Not shown. |
| gates[].pass | SymbolDiagnostics | Not shown. |
| gates[].code | SymbolDiagnostics | Not shown. |

These are informational only; no functional impact.

---

## 5. TYPE_MISMATCHES

| Location | Issue | Severity |
|----------|-------|----------|
| None identified | | |

---

## 6. HIGH RISK Runtime Breakpoints

| Risk | Location | Mitigation |
|------|----------|------------|
| None | | |

**Notes:**
- Decision artifact keys (`execution_gate` vs `execution_gate_result`): Backend returns both; Dashboard uses `execution_gate`.
- Optional chaining (`?.`) is used where data may be missing.
- `symbol_eligibility` and `liquidity` are guarded with truthiness checks before use.

---

## 7. Artifact Switching Flow (useDecision)

### How useDecision(mode, filename?) builds the URL

```ts
// queries.ts
export function useDecision(mode: DecisionMode, filename?: string) {
  const path =
    filename && filename !== "decision_latest.json"
      ? decisionFilePath(filename, mode)   // /api/ui/decision/file/{filename}?mode={mode}
      : decisionLatestPath(mode);         // /api/ui/decision/latest?mode={mode}
  return useQuery({ ... });
}
```

### Is filename optional?

Yes. Second argument is optional: `filename?: string`.

### What happens when filename is undefined?

- `filename` is falsy → `path = decisionLatestPath(mode)` → `GET /api/ui/decision/latest?mode={mode}`
- Query runs and returns latest decision artifact.

### What happens when filename is "decision_latest.json"?

- Treated like undefined: `path = decisionLatestPath(mode)` → `GET /api/ui/decision/latest?mode={mode}`
- Avoids redundant `/api/ui/decision/file/decision_latest.json`.

### Flow Summary

| filename value | URL |
|----------------|-----|
| `undefined` | `/api/ui/decision/latest?mode=LIVE` |
| `""` | `/api/ui/decision/latest?mode=LIVE` |
| `"decision_latest.json"` | `/api/ui/decision/latest?mode=LIVE` |
| `"decision_2026-02-15T05Z.json"` | `/api/ui/decision/file/decision_2026-02-15T05Z.json?mode=LIVE` |

---

## 8. x-ui-key Header Wiring in client.ts

```ts
// client.ts
const UI_KEY = (_env?.VITE_UI_KEY ?? "").trim();

function getHeaders(): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  if (UI_KEY) h["x-ui-key"] = UI_KEY;
  return h;
}

// apiGet uses getHeaders() on every request
const res = await fetch(url, { method: "GET", headers: getHeaders() });
```

### Confirmation

| Check | Status |
|-------|--------|
| Reads `VITE_UI_KEY` from env | Yes |
| Sends `x-ui-key` only when non-empty | Yes |
| Header name `x-ui-key` | Yes (lowercase) |
| Applied to all apiGet requests | Yes |

Backend expects `x-ui-key` when `UI_API_KEY` is set; client sends it when `VITE_UI_KEY` is set. Match is correct.

---

## 9. Summary

| Category | Count | Status |
|----------|-------|--------|
| MISSING_FIELDS (critical) | 0 | OK |
| MISSING_FIELDS (low risk) | 4 | Handled |
| UNUSED_FIELDS | 15+ | Informational |
| TYPE_MISMATCHES | 0 | OK |
| HIGH RISK breakpoints | 0 | OK |
| useDecision flow | | Correct |
| x-ui-key wiring | | Correct |
