# DATA_REQUIREMENTS — Authoritative ORATS Integration Contract

Single source of truth for ChakraOps ORATS data. All UI, evaluation, and diagnostics MUST follow this contract. Implemented in `app/core/data/data_requirements.py`.

## Non-negotiable rules

1. **Single authoritative snapshot**  
   All consumers (Universe, Ticker, evaluation, diagnostics) use the same canonical snapshot from `app/core/data/symbol_snapshot_service.py`. No per-page ORATS wiring.

2. **No field named `avg_volume`**  
   That field does not exist in ORATS. Do not use it anywhere.

3. **Volume metrics ONLY**
   - **avg_option_volume_20d** — from `/datav2/cores` (ORATS field `avgOptVolu20d`).
   - **avg_stock_volume_Nd** — derived from `/datav2/hist/dailies` using `stockVolume` (e.g. mean of last 20 trading days).

4. **Equity price / bid / ask / volume**  
   ONLY from delayed `/strikes/options` with underlying tickers. No other source.

5. **Live endpoints**  
   MUST NOT be used for equity quote (bid/ask/volume) or iv_rank. Use delayed only.

6. **Stage-1 HARD GATE**  
   If any required field is missing or stale → BLOCK. No WARN + PASS. Evaluation must not proceed with missing or stale required data.

## Required Stage-1 fields

All must be present and not stale; source is delayed data only:

| Field        | Source                          |
|-------------|----------------------------------|
| price       | Delayed `/strikes/options`       |
| bid         | Delayed `/strikes/options`       |
| ask         | Delayed `/strikes/options`       |
| volume      | Delayed `/strikes/options`       |
| quote_date  | Delayed `/strikes/options`       |
| iv_rank     | Delayed `/ivrank`                |

Missing any → BLOCK. Stale (> 1 trading day) → BLOCK.

## Volume (allowed only)

| Canonical name           | ORATS source                    | Notes                    |
|--------------------------|---------------------------------|--------------------------|
| stock_volume_today        | `/datav2/cores` → stkVolu       | Today’s stock volume     |
| avg_option_volume_20d    | `/datav2/cores` → avgOptVolu20d | 20-day avg options vol   |
| avg_stock_volume_20d     | Derived from `/datav2/hist/dailies` | Mean of last 20 days stockVolume |

## Testing requirements

- Fail if a **non-existent field** (e.g. `avg_volume`) is referenced.
- Fail if a **required derived field** is not computed when required.
- Fail if **live endpoints** are used for equity quotes.
- Fail if **Stage-1** allows evaluation to proceed with missing or stale required data.

## References

- [ORATS_DATAV2_ENDPOINT_AND_DATA_REFERENCE.md](./ORATS_DATAV2_ENDPOINT_AND_DATA_REFERENCE.md)
- [DATA_CONTRACT.md](./DATA_CONTRACT.md) — BLOCKED/WARN/PASS semantics and overrides (Stage-1 gate overrides: missing/stale → BLOCK).
