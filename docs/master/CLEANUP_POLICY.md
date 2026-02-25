# ChakraOps Cleanup Policy

**Purpose:** Define what constitutes repo bloat, what to keep vs delete, and how to perform safe cleanup without losing release evidence or breaking gates.

---

## 1. Categories of repo bloat

| Category | Description | Examples |
|----------|-------------|----------|
| **Legacy phase/plan docs** | Old phase plans (e.g. phase0_keep_list, phase4_plan, PHASE_8_PLAN) that are superseded by master PRD and roadmap | `chakraops/docs/phase4_plan.md`, `chakraops/docs/PHASE_8_PLAN.md` |
| **Redundant verification** | Duplicate or obsolete verification files (e.g. same release verified twice with different names) | Only if clearly duplicate; never remove current `out/verification/<Release>/notes.md` for a completed release |
| **Old fixtures** | Test fixtures or sample JSON no longer referenced by any test | Grep for references before deleting |
| **One-off reports** | Single-purpose audit or report docs (e.g. DELTA_GATE_FIX_SUMMARY, FRONTEND_BACKEND_WIRING_AUDIT) that are historical only | Move to archive if still useful for reference |
| **Superseded design docs** | Design or enhancement docs replaced by master PRD / roadmap / release requirements | `chakraops/docs/enhancements/` items that are now covered in master docs |
| **Scratch or temp** | Any file under `out/` that is not on the whitelist (see RELEASE_CHECKLIST) | Remove per whitelist; do not add new artifact types without release note |

---

## 2. Rules: what to keep vs delete

### Always keep

- **Release evidence:** For every release marked DONE in RELEASE_CHECKLIST: keep `chakraops/docs/releases/<Release>_release_notes.md` (or equivalent) and `out/verification/<Release>/notes.md`. Do **not** delete these.
- **Master docs:** `docs/master/*.md` (PRD, roadmap, playbook, backlog, cleanup policy).
- **Current release checklist:** `chakraops/docs/releases/RELEASE_CHECKLIST.md`.
- **Release notes template:** `chakraops/docs/releases/RELEASE_NOTES_TEMPLATE.md`.
- **Active requirements:** `chakraops/docs/releases/<Release>_requirements.md` for releases in progress or recent (e.g. R24.x, R25.x).
- **Canonical design:** Decision store, data contract, and runbook docs that are referenced by code or operations (e.g. DECISION_STORE_CANONICAL, RUNBOOK_*).
- **Test-referenced files:** Any fixture or doc that is imported or referenced by tests (grep before delete).

### May remove or archive

- **Legacy phase docs:** If superseded by master PRD/roadmap, move to `docs/archive/` (or delete if no historical value). Prefer **move** over delete for first pass.
- **One-off audit reports:** Move to `docs/archive/audits/` or similar if worth keeping; else delete.
- **Redundant verification:** Only if two dirs exist for the *same* release (e.g. typo duplicate); keep the one referenced in RELEASE_CHECKLIST.
- **Old fixtures:** After confirming no test references, delete or move to `tests/fixtures/archive/`.

### Never delete

- Any `out/verification/<Release>/notes.md` for a release that is checked DONE in RELEASE_CHECKLIST.
- Any release notes file for a release that is checked DONE.
- `.gitignore` or security-related config; env templates (without secrets).
- Files required by tests (run test suite before and after cleanup).

---

## 3. docs/archive/ approach

- **Create:** `docs/archive/` (or `chakraops/docs/archive/` if preferred) for superseded design and phase docs.
- **Structure (optional):** `docs/archive/phase_plans/`, `docs/archive/audits/`, `docs/archive/superseded/`.
- **Index:** Add a short `docs/archive/README.md` listing what was moved and why (e.g. "Phase 4 plan moved 2026-XX; superseded by ROADMAP_2026.md").
- **Do not archive:** Release notes or verification notes; keep those in place.

---

## 4. out/ hygiene (reminder)

- **Whitelist (from RELEASE_CHECKLIST):** `decision_latest.json`, `slack_status.json`, `universe_overrides.json`, `eval_snapshot.json`, `verification/<Release>/`, `evaluations/`, `alerts/`, `lifecycle/`, optional `mtf_cache/`.
- **Retention:** Decision history per symbol: keep last K runs (DECISION_ARCHIVE_MAX / DECISION_HISTORY_KEEP). Prune via `prune_decision_archives()` or documented script.
- **Never commit:** Secrets, `.env`, API keys; keep `out/` and secrets in `.gitignore`.

---

## 5. Safe cleanup checklist

Use this before and during any cleanup run:

- [ ] **Read this policy** and RELEASE_CHECKLIST (out/ whitelist and release evidence).
- [ ] **List candidates:** Identify files/dirs to move or delete; grep for references (tests, imports, links).
- [ ] **Do not touch:** `out/verification/<Release>/notes.md` and release notes for DONE releases; RELEASE_CHECKLIST; master docs; test-referenced fixtures.
- [ ] **Archive preferred:** For legacy/superseded docs, move to `docs/archive/` with README note rather than delete.
- [ ] **Run gates after cleanup:** `cd chakraops && python -m pytest -v --tb=short`; `cd frontend && npm run test -- --run`; `cd frontend && npm run build`. All must pass.
- [ ] **Commit with clear message:** e.g. "chore: archive legacy phase docs per CLEANUP_POLICY; no release evidence removed."

---

*This policy is the single source of truth for what can be safely removed or archived. When in doubt, keep or archive; do not delete release evidence.*
