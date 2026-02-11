# Validate One Symbol — Manual Runbook

Single-ticker smoke: call the running API, save real JSON to `artifacts/validate/`, and print a compact summary. **Server must already be running**; this script does not start it.

---

## Prerequisites

1. **API server running** at `http://127.0.0.1:8000` (or override with `--base`).
2. From repo root (the `chakraops` folder):

   ```bash
   # Terminal 1: start server
   uvicorn app.api.server:app --port 8000
   ```

   Leave it running.

---

## Exact commands

### 1. Run validation (default symbol: AMD)

```bash
python scripts/validate_one_symbol.py
```

- Writes:
  - `artifacts/validate/AMD_ops_snapshot.json` — from `GET /api/ops/snapshot?symbol=AMD`
  - `artifacts/validate/AMD_symbol_diagnostics.json` — from `GET /api/view/symbol-diagnostics?symbol=AMD`
  - `artifacts/validate/universe.json` — from `GET /api/view/universe` (optional; skipped if non-200)
- Prints a compact summary: `snapshot_time`, `stock.price` / `bid` / `ask` / `volume` / `quote_as_of` / `iv_rank`, `missing_reasons` keys, `field_sources` keys.

### 2. Use another symbol

```bash
python scripts/validate_one_symbol.py --symbol AAPL
```

- Writes `artifacts/validate/AAPL_ops_snapshot.json` and `artifacts/validate/AAPL_symbol_diagnostics.json`.

### 3. Use a different base URL

```bash
python scripts/validate_one_symbol.py --base http://localhost:9000
```

---

## Exit codes

- **0** — All requested endpoints returned 200 and JSON was saved.
- **1** — One or more requests failed (e.g. connection refused, non-200, or invalid JSON).

---

## Automated test (mocked; no live ORATS)

To assert the **contract** (200, required keys, no `"UNKNOWN"` placeholders for required fields) without hitting the network:

```bash
python -m pytest tests/test_runtime_contract_one_symbol_mocked.py -v
```

Requires FastAPI; tests are skipped if FastAPI is not installed.
