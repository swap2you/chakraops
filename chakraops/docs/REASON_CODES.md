# Reason Codes → Plain-English Mapping

Internal codes are kept for debugging. The UI shows **reasons_explained** (title + message with key numbers). This document is the code → English mapping and required metrics per code.

---

## API shape

`reasons_explained` is a list of:

- **code**: Internal code (e.g. `rejected_due_to_delta`, `DATA_INCOMPLETE`).
- **severity**: `FAIL` or `WARN`.
- **title**: Short label for the reason.
- **message**: Plain-English sentence with key numbers where applicable.
- **metrics**: Optional object with numeric/string details for tooling or drill-down.

---

## Code → English mapping and metrics

| Code | Title | Message pattern | Metrics |
|------|--------|------------------|--------|
| **rejected_due_to_delta** | Delta outside target range | “Delta {observed_delta_decimal} ({observed_delta_pct}%) outside target range {target_range_decimal}.” Or parsed from primary e.g. “rejected_due_to_delta=32” → “Delta 0.32 (decimal) outside target range 0.20–0.40.” | observed_delta_decimal, observed_delta_pct, target_range_decimal |
| **DATA_INCOMPLETE** | Data incomplete | “Required data missing: {list}.” | required_data_missing |
| **FAIL_RSI_RANGE** | RSI outside preferred range | “RSI {value} not in required range {lo}–{hi}.” or “RSI outside preferred range.” | — |
| **FAIL_NOT_NEAR_SUPPORT** | Not near support | “Not near support: distance {pct}% > tolerance {pct}%.” or “Not near support.” | — |
| **FAIL_NO_HOLDINGS** | No shares held | “No shares held; covered calls disabled.” | — |
| **CONTRACT_SELECTION_FAIL** | No contract passed filters | Primary reason or “No contracts passed option liquidity and delta filters.” | — |
| **OTHER** | Reason | Primary reason text as-is. | — |

---

## Examples (message only)

- **Delta**: “Delta 0.32 (32%) outside target range 0.15–0.35.”
- **RSI**: “RSI 44.9 not in required range 45–70.”
- **Support**: “Not near support: distance 1.8% > tolerance 0.6%.”
- **Data**: “Required data missing: resistance_level, ATR14.”
- **Holdings**: “No shares held; covered calls disabled.”

---

## Implementation

- **Server**: `app/core/eval/reason_codes.py` — `explain_reasons(...)`.
- **Consumers**: Evaluation service v2 sets `reasons_explained` on `SymbolDiagnosticsDetails`; UI routes expose it on symbol diagnostics and universe symbols. Raw `primary_reason` remains for debug.
