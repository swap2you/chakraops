# Field Waivers Audit

**All waivers identified in the codebase.** Validation only; no logic changes.

---

## Search patterns used

- `waived_fields`
- `optional_not_available`
- `ALLOW_MISSING`
- `skip_if_missing`

---

## 1. waived_fields (Stage 2 OPRA waiver) — REMOVED

**REMOVED (as of strict Stage-1 cleanup).** Equity bid/ask/volume are **required** Stage 1 fields from delayed `/datav2/strikes/options`. If missing or stale, Stage 1 BLOCKs; no waiver. The code path that removed bid, ask, volume, bidsize, asksize from `missing_fields` when Stage 2 OPRA passed has been deleted from `app/core/eval/staged_evaluator.py`. `waived_fields` no longer includes these fields anywhere.

---

## 2. optional_not_available

| Location | Field(s) | Why Waived | Is This Still Valid? | Should Be Removed? |
|----------|----------|------------|----------------------|--------------------|
| `app/core/orats/orats_equity_quote.py` — `FullEquitySnapshot.optional_not_available` | Dict; no `avg_volume` or other keys in current contract | Optional fields that are "not available from ORATS" do not affect completeness. Previously used for avg_volume (removed). | Yes. Contract forbids avg_volume; no field currently populated here in canonical path. | No. Keep for future optional fields that are explicitly "not available" from any endpoint. |

---

## 3. ALLOW_MISSING

| Result |
|--------|
| **Not found** in app code. No ALLOW_MISSING pattern. |

---

## 4. skip_if_missing

| Result |
|--------|
| **Not found** in app code. No skip_if_missing pattern. |

---

## Summary

- **Waived fields (stock bid/ask/volume):** REMOVED. Stage 1 strictly requires price, bid, ask, volume, quote_date, iv_rank; missing → BLOCK.
- **optional_not_available:** Present on FullEquitySnapshot; currently empty in canonical snapshot path; valid to keep.
- **ALLOW_MISSING / skip_if_missing:** Not used.
