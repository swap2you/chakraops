# Runtime Rules (Non-Negotiables)

**Applies to:** All runtime code paths in the ChakraOps repo. No exceptions.

---

## 1. Single upstream data source: ORATS only

- **ORATS is the only upstream data source allowed.**
- No Theta, no yfinance, no alternate providers in runtime code paths.
- If any such code exists, it must be removed from active paths (archived only; not imported by runtime).

---

## 2. Stage-1 required fields (hard gate)

- **Required:** price, bid, ask, volume, quote_date, iv_rank.
- All must be **present**. If any is **missing** or **stale** → verdict **BLOCKED**.
- **No waivers.** No OPRA or other waiver that removes these from missing_fields or bypasses BLOCK.

---

## 3. Earnings and news: optional only

- Earnings and news are **OPTIONAL** only.
- They must **never** cause a BLOCK.
- They may influence score or be displayed in UI.

---

## 4. Canonical snapshot for UI

- All UI-facing pages must be wired from the **same canonical snapshot object**.
- No parallel fetches that bypass or duplicate the canonical snapshot pipeline.
- **Evaluation view:** `/api/view/evaluation/latest` and related view APIs read from **canonical run artifacts** when present (`artifacts/runs/latest.json` → that run’s `evaluation.json`). Single source of truth produced by the evaluation runner.

---

## 5. Evaluation runner and artifacts (Phase 3)

- **Schedule:** During market hours (9:30–16:00 ET, weekdays), evaluation runs every **30 minutes** (env `UNIVERSE_EVAL_MINUTES`, default 30). Outside market hours: no auto-run; on-demand only via `POST /api/ops/evaluate-now`.
- **Artifacts:** Completed runs write to `artifacts/runs/YYYY-MM-DD/run_YYYYMMDD_HHMMSSZ/` (snapshot.json, evaluation.json, summary.md), `latest.json`, and `recent.json` (last 3 runs). Purge removes runs older than 10 days.
- **Details:** See **docs/RUNNER_AND_ARTIFACTS.md**.

---

## 6. Single-ticker validation script

- Maintain a **single-ticker validation script** that produces JSON artifacts under **artifacts/validate/**.
- Script must assume server is already running (no auto-start). Default symbol (e.g. AMD) and endpoints as documented (e.g. docs/VALIDATE_ONE_SYMBOL.md).

---

## References

- **Data contract:** docs/ORATS_DATA_TRUTH_TABLE.md, docs/DATA_REQUIREMENTS.md
- **Field waivers:** docs/FIELD_WAIVERS.md (waiver removed; bid/ask/volume required)
- **Validation runbook:** docs/VALIDATE_ONE_SYMBOL.md
- **Runner and artifacts:** docs/RUNNER_AND_ARTIFACTS.md
