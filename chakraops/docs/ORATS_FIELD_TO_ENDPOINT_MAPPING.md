# ORATS Field-to-Endpoint Mapping & Known Not-Available Fields

ChakraOps uses ORATS datav2 for equity quotes and IV rank. This page summarizes **which endpoint provides which field** and **which fields are not available** (do not fabricate).

**Source of truth:** See [OratsUtil docs: ORATS_DATAV2_ENDPOINT_AND_DATA_REFERENCE.md](https://github.com/your-org/OratsUtil/blob/main/docs/ORATS_DATAV2_ENDPOINT_AND_DATA_REFERENCE.md) (or the copy under `C:\Development\Workspace\OratsUtil\docs\`) for full endpoint specs, query params, and response shapes.

---

## 1. ORATS Field-to-Endpoint Mapping

| ChakraOps field | ORATS endpoint | ORATS field(s) | Notes |
|-----------------|----------------|----------------|--------|
| **price** | `GET /datav2/strikes/options` | `stockPrice` | Underlying tickers only; max 10 per request |
| **bid** | `GET /datav2/strikes/options` | `bid` | Underlying rows only (no `optionSymbol`) |
| **ask** | `GET /datav2/strikes/options` | `ask` | |
| **volume** | `GET /datav2/strikes/options` | `volume` | |
| **quote_time** | `GET /datav2/strikes/options` | `quoteDate` | ISO UTC |
| **iv_rank** | `GET /datav2/ivrank` | `ivRank1m` else `ivPct1m` | Max 10 tickers per request |

- **Equity quote fields** (price, bid, ask, volume, quoteDate) come **only** from delayed **`/strikes/options`** with **underlying tickers** in `tickers=`. Live endpoints do not return equity-level bid/ask/volume.
- **IV rank** comes from delayed **`/ivrank`** with `ticker=` (comma-delimited, max 10).
- **Mixed-row safety:** `/strikes/options` can return both underlying rows and option rows (when OCC symbols are requested). ChakraOps parses **only rows without `optionSymbol`** as equity snapshots.

---

## 2. MarketSnapshot Contract (ChakraOps Signal Engine)

**Required fields:** `price`, `bid`, `ask`, `volume`, `quote_time`, `iv_rank`.

**Optional:** Live-derived fields only when available.

**Explicitly excluded from required:** `avg_volume` — not provided by any ORATS endpoint; never blocks evaluation. See [Known Not-Available Fields](#3-known-not-available-fields) below.

---

## 3. Known Not-Available Fields

These fields are **not** returned by the ORATS datav2 endpoints used by ChakraOps. Do **not** fabricate values; treat as missing and document.

| Field | Reason |
|-------|--------|
| **avg_volume** | Not returned by any of the 8 ORATS datav2 endpoints. Mark as optional / NOT_AVAILABLE with reason; do not add to required completeness. |

- **Equity bid/ask/volume from live endpoints:** Live endpoints do not return equity-level quote fields; only delayed `/strikes/options` with underlying tickers does.
- **Real-time equity quote:** Delayed data is 15 min behind; live endpoints do not provide underlying bid/ask/volume.

---

## 4. Configuration

- **Token:** Set `ORATS_API_TOKEN` in environment (or use app config). Required for all ORATS requests.
- **Evaluation quote window:** Config key `EVALUATION_QUOTE_WINDOW_MINUTES` (env: `EVALUATION_QUOTE_WINDOW_MINUTES`). Default: **30** minutes. Used for reporting/staleness context.

---

## 5. Further Reading

- [DATA_CONTRACT.md](./DATA_CONTRACT.md) — Required vs optional data, staleness, BLOCKED/WARN/PASS.
- [RUNBOOK.md](./RUNBOOK.md) — How to run smoke tests and health checks (ORATS connectivity).
