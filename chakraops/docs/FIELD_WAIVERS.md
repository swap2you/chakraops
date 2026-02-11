# Field Waivers Audit

**All waivers identified in the codebase.** Validation only; no logic changes.

---

## Search patterns used

- `waived_fields`
- `optional_not_available`
- `ALLOW_MISSING`
- `skip_if_missing`

---

## 1. waived_fields (Stage 2 OPRA waiver)

| Location | Field(s) | Why Waived | Is This Still Valid? | Should Be Removed? |
|----------|----------|------------|----------------------|--------------------|
| `app/core/eval/staged_evaluator.py` (STOCK_INTRADAY_FIELDS) | **bid**, **ask**, **volume**, bidsize, asksize | When Stage 2 OPRA path confirms options liquidity (`stage2.liquidity_ok`), stock intraday fields are removed from `missing_fields` and added to `waived_fields`. Completeness is boosted; gate shows "Stock bid, ask, volume waived - options liquidity confirmed (DERIVED_FROM_OPRA)". | By design: options liquidity is treated as sufficient so missing underlying quote is not BLOCK. | **FLAG: BUG** — Auditor rule: *If bid / ask / volume appear here → flag as BUG.* Required Stage 1 fields (bid, ask, volume) are being waived when OPRA passes. Product decision: either accept waiver explicitly or remove it and BLOCK when stock quote missing. |

**Evidence:** `out/evaluations/*_data_completeness.json` frequently contains `"waived_fields": ["bid", "ask", "volume"]` for symbols (e.g. ABNB, AMZN, COIN, CRWD).

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

- **Waived fields in production:** **bid**, **ask**, **volume** (and optionally bidsize, asksize) when OPRA confirms options liquidity. **Flagged as BUG** per audit rule.
- **optional_not_available:** Present on FullEquitySnapshot; currently empty in canonical snapshot path; valid to keep.
- **ALLOW_MISSING / skip_if_missing:** Not used.
