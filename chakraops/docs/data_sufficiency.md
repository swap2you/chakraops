# Data Sufficiency — Field Reference

Phase 5: Data coverage for symbol/position. Auto-derived from evaluation; manual overrides logged distinctly.

## Status Values

| Value | Meaning |
|-------|---------|
| PASS | data_completeness ≥ 0.9 |
| WARN | 0.75 ≤ data_completeness < 0.9 |
| FAIL | data_completeness < 0.75 or derivation error |

## When Computed

- **Auto-derived:** From latest evaluation run `data_completeness` per symbol.
- **Manual override:** When `data_sufficiency_override` is set on Position; source logged as MANUAL.

## When UNKNOWN / FAIL

- No evaluation data → FAIL, `missing_fields` = ["no_evaluation_data"]
- Symbol not in latest evaluation → FAIL, `missing_fields` = ["symbol_not_in_latest_evaluation"]
- Derivation error → FAIL, `missing_fields` = ["derivation_error"]

## API Response (GET /api/symbols/{symbol}/data-sufficiency)

| Field | Meaning | Always Present |
|-------|---------|----------------|
| `symbol` | Uppercase ticker | Yes |
| `status` | PASS \| WARN \| FAIL | Yes |
| `missing_fields` | List of missing field names | Yes (empty list when PASS) |

## Position Detail (GET /api/positions/tracked/{position_id})

| Field | Meaning | Always Present |
|-------|---------|----------------|
| `data_sufficiency` | Effective status | Yes |
| `data_sufficiency_missing_fields` | List of missing fields | Yes (empty when PASS or override) |
| `data_sufficiency_is_override` | True if manual override used | Yes |

## UI Interpretation

- **status = WARN or FAIL:** Always show `missing_fields` list when non-empty. Do not hide.
- **missing_fields non-empty:** UI should display which fields are missing for transparency.
- **is_override = true:** Indicate that the user manually overrode the auto-derived value.
- Do not treat missing `data_sufficiency` as PASS; if absent, treat as FAIL.
