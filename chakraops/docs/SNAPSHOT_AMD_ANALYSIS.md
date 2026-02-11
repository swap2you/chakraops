# Snapshot AMD Analysis

**Factual summary of GET /api/ops/snapshot?symbol=AMD.** No interpretation; facts only.

To populate: run the API server (`uvicorn app.api.server:app --port 8000`), then:

```bash
python scripts/capture_snapshot_amd.py
```

Then paste or inspect `artifacts/snapshot_AMD.json` and fill the sections below (or run a script that reads that file and outputs this structure).

---

## snapshot_time

(From top-level `snapshot_time` in response.)

| Key | Value |
|-----|--------|
| snapshot_time | *[ISO string from response]* |

---

## Fields present (from snapshot)

(From `response["snapshot"]` — every key that has a non-null value.)

| ChakraOps field | Value | Source (field_sources) |
|-----------------|-------|------------------------|
| ticker | | |
| price | | |
| bid | | |
| ask | | |
| volume | | |
| quote_date | | |
| iv_rank | | |
| stock_volume_today | | |
| avg_option_volume_20d | | |
| avg_stock_volume_20d | | |
| quote_as_of | | |
| core_as_of | | |
| derived_as_of | | |

---

## missing_reasons

(From `response["missing_reasons"]` — every key and message.)

| Field | Reason |
|-------|--------|
| *[field]* | *[message]* |

---

## field_sources

(From `response["field_sources"]` — which endpoint supplied each present field.)

| Field | Source (ChakraOps label) | ORATS endpoint |
|-------|--------------------------|----------------|
| price | delayed_strikes_ivrank | /datav2/strikes/options |
| bid | delayed_strikes_ivrank | /datav2/strikes/options |
| ask | delayed_strikes_ivrank | /datav2/strikes/options |
| volume | delayed_strikes_ivrank | /datav2/strikes/options |
| quote_date | delayed_strikes_ivrank | /datav2/strikes/options |
| iv_rank | delayed_strikes_ivrank | /datav2/ivrank (merged with strikes/options in pipeline) |
| stock_volume_today | datav2/cores | /datav2/cores |
| avg_option_volume_20d | datav2/cores | /datav2/cores |
| avg_stock_volume_20d | DERIVED_ORATS_HIST | /datav2/hist/dailies (derived) |

*(Fill with actual keys from response; add/remove rows as needed.)*

---

## Endpoint → fields supplied

| ORATS endpoint | Fields supplied |
|----------------|-----------------|
| /datav2/strikes/options | price, bid, ask, volume, quote_date (underlying row) |
| /datav2/ivrank | iv_rank (ivRank1m / ivPct1m) |
| /datav2/cores | stock_volume_today (stkVolu), avg_option_volume_20d (avgOptVolu20d) |
| /datav2/hist/dailies | avg_stock_volume_20d (derived: mean of last 20 stockVolume) |

*(Confirm from actual `field_sources` in response.)*
