# Data Sufficiency — Field Reference (Phase 5/6)

Phase 6: Data sufficiency is **structurally** derived from [data_dependencies.md](./data_dependencies.md). Manual overrides cannot override missing REQUIRED data.

## Status Values (Phase 6)

| Value | Meaning |
|-------|---------|
| PASS | `required_data_missing` empty AND `required_data_stale` empty |
| WARN | `optional_data_missing` non-empty OR `required_data_stale` non-empty (no required missing) |
| FAIL | `required_data_missing` non-empty |

No decision may appear PASS when required data is missing or when the system has not evaluated the symbol.

## When Computed

- **Auto-derived:** From dependency lists: `required_data_missing`, `optional_data_missing`, `required_data_stale` (see data_dependencies.md).
- **Manual override:** When `data_sufficiency_override` is set on Position; **MUST NOT** override when `required_data_missing` is non-empty. Override source logged as MANUAL.

## When FAIL

- No evaluation data → FAIL, `required_data_missing` = ["no_evaluation_data"]
- Symbol not in latest evaluation → FAIL, `required_data_missing` = ["symbol_not_in_latest_evaluation"]
- Any required field missing (price, iv_rank, bid, ask, volume, or delta for candidate) → FAIL

## API Response (GET /api/symbols/{symbol}/data-sufficiency)

| Field | Meaning | Always Present |
|-------|---------|----------------|
| `symbol` | Uppercase ticker | Yes |
| `status` | PASS \| WARN \| FAIL | Yes |
| `missing_fields` | Combined missing (required + optional) | Yes (empty when PASS) |
| `required_data_missing` | Required fields missing | Yes (empty when PASS) |
| `optional_data_missing` | Optional fields missing | Yes |
| `required_data_stale` | Required fields stale (> 1 trading day) | Yes |
| `data_as_of_orats` | Provider timestamp (ORATS) | When available |
| `data_as_of_price` | Price data timestamp | When available |

## Position Detail (GET /api/positions/tracked/{position_id})

Includes `data_sufficiency`, `data_sufficiency_missing_fields`, `data_sufficiency_is_override`, plus Phase 6: `required_data_missing`, `optional_data_missing`, `required_data_stale`, `data_as_of_orats`, `data_as_of_price`.

## UI Interpretation

- **status = WARN or FAIL:** Always show `missing_fields` and `required_data_missing` when non-empty.
- **required_data_stale non-empty:** Show explicit message e.g. "Data stale (last updated N trading days ago)".
- **is_override = true:** Indicate manual override; override is invalid when required data is missing.
- Do not treat missing `data_sufficiency` as PASS; if absent, treat as FAIL.
