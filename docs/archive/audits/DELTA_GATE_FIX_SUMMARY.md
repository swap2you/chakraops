# Delta Gate Rejection Regression — Fix Summary

## Root cause

- **V2 path (CSP/CC)**: ORATS API returns delta in **percent** (e.g. 30 for 0.30). The gate used `abs(float(c["delta"]))` without normalizing to decimal, so 30 was compared to [0.20, 0.40] and failed.
- **Explanation mismatch**: When no sample was available, the UI parsed the number in `rejected_due_to_delta=N` as a delta value (e.g. 30 → 0.30) and showed "Delta 0.30 (decimal) outside target range 0.20–0.40", which is wrong when the gate actually uses abs(delta) and 0.30 is inside the band. The `N` is often the **rejection count**, not the delta.

## Fix (minimal)

1. **V2 delta normalization** (`csp_chain_v2.py`, `cc_chain_v2.py`):
   - When building candidates, set `c["delta"] = _delta_to_decimal(delta_raw)` so delta is canonical decimal in [-1, 1].
   - Gate unchanged: `d_abs = abs(c["delta"])`, `delta_lo <= d_abs <= delta_hi`. No threshold or strategy change.

2. **V2 sample for explainable reasons**:
   - When a contract fails the delta gate, append to `sample_rejected_due_to_delta` with `observed_delta_decimal_raw`, `observed_delta_decimal_abs`, `observed_delta_pct_abs`, `target_range_decimal`.
   - `staged_evaluator` merges `trace["sample_rejected_due_to_delta"]` into `result.top_rejection_reasons` so the UI gets real values.

3. **reason_codes.py**:
   - When a sample exists: message uses `observed_delta_decimal_abs` and says **"abs(delta) X (Y%) outside target range …"** so it matches the gate.
   - When no sample: generic message "No put contracts in delta band (abs(delta) 0.20–0.40). See diagnostics for details." so we do not interpret the code’s number as delta.

4. **Decision JSON**: Unchanged. `primary_reason` remains a code string (e.g. `rejected_due_to_delta=30`). `reasons_explained` is only in API/diagnostics (already present in diagnostics_by_symbol; no new persistence).

5. **Retention**: `DECISION_ARCHIVE_MAX` env (e.g. 50) configures max decision history files per symbol; `DECISION_HISTORY_KEEP` still supported. `.gitignore` includes `out/`.

## How verified

- **Backend**: `python -m pytest -q` — 520 passed.
- **Regression tests** (`tests/_core/test_delta_decimal_canonical.py`): CSP put -0.31 passes abs band; call +0.31 passes; put -0.45 fails; raw 32 → 0.32 then abs check passes.
- **reason_codes**: Tests expect "abs(delta)" in message and sample with `observed_delta_decimal_abs`.
- **Manual**: Re-run single-symbol recompute for HD; Stage-2 delta should not fail when abs(delta) is in [0.20, 0.40]. Gate Summary message should be consistent (e.g. "abs(delta) 0.31 (31%) outside …" only when 0.31 is actually outside the band).
