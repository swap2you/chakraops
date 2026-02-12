# Validate One Symbol — Manual Runbook

Single-ticker **runtime validation**: calls the running API, saves JSON and a markdown analysis to `artifacts/validate/`, and runs a deterministic contract assertion (required fields, Stage-1 verdict). **Server must already be running**; the script does not start it. No cached DB reads for validation outputs.

Exact checks and exit codes: **docs/VALIDATE_ONE_SYMBOL_EXPECTATIONS.md**.

---

## Prerequisites

1. **API server running** at `http://127.0.0.1:8000` (or override with `--base`).
2. From the `chakraops` folder:

   ```bash
   # Terminal 1: start server
   uvicorn app.api.server:app --port 8000
   ```

   Leave it running.

---

## Exact commands

### 1. Run validation (default symbol: SPY)

```bash
cd chakraops
python scripts/validate_one_symbol.py
```

- Calls:
  - **GET /api/ops/snapshot?symbol=SPY**
  - **GET /api/view/symbol-diagnostics?symbol=SPY**
  - **GET /api/view/universe**
- Writes:
  - `artifacts/validate/SPY_ops_snapshot.json`
  - `artifacts/validate/SPY_symbol_diagnostics.json`
  - `artifacts/validate/universe.json`
  - `artifacts/validate/SPY_analysis.md` (human-readable)
- Prints a compact summary and, if any required field is missing or Stage-1 is BLOCKED, the BLOCK reason and which field(s).

### 2. Use another symbol

```bash
python scripts/validate_one_symbol.py --symbol AMD
```

- Writes `artifacts/validate/AMD_ops_snapshot.json`, `AMD_symbol_diagnostics.json`, `AMD_analysis.md`, and `universe.json`.

### 3. Different base URL

```bash
python scripts/validate_one_symbol.py --base http://localhost:9000
```

---

## Exit codes (contract assertion)

| Code | Meaning |
|------|---------|
| **0** | All required fields present and quote_date fresh; Stage-1 would PASS. |
| **1** | Request/IO error (e.g. connection refused, non-200, invalid JSON). |
| **2** | One or more required fields missing or null. |
| **3** | Stage-1 verdict BLOCKED (e.g. quote_date stale). |

---

## Sample console output format

Success (exit 0):

```
Wrote artifacts/validate/SPY_ops_snapshot.json
Wrote artifacts/validate/SPY_symbol_diagnostics.json
Wrote artifacts/validate/universe.json
Wrote artifacts/validate/SPY_analysis.md

--- Summary ---
snapshot_time: 2026-02-10T...
price: 585.12
bid: 584.98
ask: 585.25
volume: 98234500
quote_as_of / quote_date: 2026-02-10
iv_rank: 42.5
missing_reasons (required keys): []
```

Failure — missing required field (exit 2):

```
Wrote ...
BLOCK reason: required field(s) missing: ['bid', 'ask']
  missing: bid (not provided by ORATS)
  missing: ask (not provided by ORATS)
```

Failure — stale (exit 3):

```
Wrote ...
BLOCK reason: quote_date stale (Stage-1)
  DATA_STALE: quote_date is 2 day(s) old (threshold 1)
```

---

## Automated test (mocked; no live ORATS)

To assert the **contract** (200, required keys) without hitting the network:

```bash
python -m pytest tests/test_runtime_contract_one_symbol_mocked.py -v
```

Requires FastAPI; tests are skipped if FastAPI is not installed.
