# Validate One Symbol — Exact Expectations

This document specifies the **exact checks** performed by `scripts/validate_one_symbol.py` to prove we fetch required fields from ORATS and wire the same snapshot through all endpoints. ORATS is the only upstream; no cached DB reads are used for validation outputs.

---

## Endpoints Called (in order)

1. **GET /api/ops/snapshot?symbol=SPY**  
   Writes: `artifacts/validate/SPY_ops_snapshot.json`

2. **GET /api/view/symbol-diagnostics?symbol=SPY**  
   Writes: `artifacts/validate/SPY_symbol_diagnostics.json`

3. **GET /api/view/universe**  
   Writes: `artifacts/validate/universe.json`

---

## Required Stage-1 Fields

The following fields **must** be present and non-null in the canonical snapshot (ops snapshot and diagnostics stock) when ORATS returns them:

| Field         | Meaning                    | Notes                          |
|---------------|----------------------------|--------------------------------|
| **price**     | Underlying price           | From delayed /strikes/options   |
| **bid**       | Bid price                  | Required; no waiver             |
| **ask**       | Ask price                  | Required; no waiver             |
| **volume**    | Share volume               | `0` is valid (not missing)      |
| **quote_date** / **quote_as_of** | Date of quote (YYYY-MM-DD) | Used for staleness              |
| **iv_rank**   | IV rank                    | From /datav2/ivrank             |

---

## Exact Checks

### 1. Ops snapshot must include required fields

- Response must have `snapshot` (or equivalent) containing: `price`, `bid`, `ask`, `volume`, `quote_as_of` or `quote_date`, `iv_rank`.
- Each of these must be **present** in the payload. Value may be `null` only if ORATS did not provide it (then the script reports missing and exits 2).

### 2. missing_reasons must be empty for required fields when ORATS returns them

- When ORATS returns data for a required field, that field must not appear in `missing_reasons` with a non-empty reason.
- If any required field is in `missing_reasons` or has a null value, the script prints the **BLOCK reason** and which field(s), then exits with code **2**.

### 3. Diagnostics must show Stage-1 PASS when fields present and quote_date fresh

- Stage-1 **PASS** means: all required fields present (non-null) and `quote_date` within the staleness window (≤ `STAGE1_STALE_TRADING_DAYS`, typically 1 trading day).
- If **Stage-1 BLOCKED** (e.g. stale quote_date, or missing field), the script prints the BLOCK reason and exits **3** (if verdict BLOCKED due to staleness) or **2** (if verdict BLOCKED due to missing field).

### 4. If any required field is missing

- The script **must** print the BLOCK reason and which field(s) (e.g. `BLOCK reason: required field(s) missing: bid, ask`).
- Exit code **2** (required field missing/null).

### 5. If Stage-1 verdict would be BLOCKED (e.g. stale)

- The script prints the BLOCK reason (e.g. `DATA_STALE: quote_date is N day(s) old`).
- Exit code **3**.

---

## Exit Codes (contract assertion)

| Code | Meaning |
|------|---------|
| **0** | All required fields present and non-null; quote_date fresh; Stage-1 would PASS. |
| **1** | Request/IO error (e.g. connection refused, non-200, invalid JSON). |
| **2** | One or more required fields missing or null. |
| **3** | Stage-1 verdict BLOCKED (e.g. quote_date stale). |

---

## Outputs

- **JSON artifacts**: `SPY_ops_snapshot.json`, `SPY_symbol_diagnostics.json`, `universe.json` (under `artifacts/validate/`).
- **Markdown analysis**: `SPY_analysis.md` (human-readable summary, required fields status, missing_reasons, Stage-1 verdict).
- **Console**: Summary of snapshot_time, field values, missing_reasons for required keys, and any BLOCK reason printed to stderr.

---

## Commands (do not start server automatically)

```bash
# Terminal 1: start server (required)
uvicorn app.api.server:app --port 8000

# Terminal 2: run validation (default symbol SPY)
cd chakraops
python scripts/validate_one_symbol.py

# With another symbol
python scripts/validate_one_symbol.py --symbol AMD

# Different base URL
python scripts/validate_one_symbol.py --base http://localhost:9000
```
