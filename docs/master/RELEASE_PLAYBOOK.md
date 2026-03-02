# ChakraOps Release Playbook

**Purpose:** Exact steps for releasing a version: SDLC gates, verification recording, UAT, rollback, and Definition of Done.  
**Companion:** `chakraops/docs/releases/RELEASE_CHECKLIST.md` (per-release checklist); `out/verification/<Release>/notes.md` (evidence).

**Phase sequencing:** Releases are executed in phase order per [ROADMAP_2026.md](ROADMAP_2026.md); current phase status is in [PHASE_STATUS.md](PHASE_STATUS.md). Do not start the next phase until the current phase’s exit criteria are met.

---

## 1. SDLC gate steps (exact commands)

Every release **must** pass these before being marked DONE. Run from **repo root** (ChakraOps).

### 1.1 Backend tests

```bash
cd chakraops
python -m pytest -v --tb=short
```

- **Pass:** Exit code 0; "passed" count and "skipped" (if any) in tail.
- **Fail:** Fix failures or skip only with documented reason; do not mark release DONE until pass (or skip explicitly allowed in checklist).

### 1.2 Frontend tests

```bash
cd frontend
npm run test -- --run
```

- **Pass:** Exit code 0; all test files passed; note "passed" and "skipped" counts.
- **Fail:** Fix or document; do not mark DONE until pass.

### 1.3 Frontend build (Preflight Build Gate)

```bash
cd frontend
npm run build
```

- **Pass:** Exit code 0; "built in Xs" or equivalent.
- **Fail:** Fix type/build hygiene; document in release notes; do not mark DONE until pass.

### 1.4 Gate policy: when scoped vs full-suite

**When scoped backend gates are allowed**

- **Doc-only releases:** No backend gates required; allowed if desired.
- **Frontend-only changes:** Backend full suite optional; must run frontend tests and frontend build.
- **Ops-only releases (scripts + docs):** Scoped backend gate allowed or skip; must record explicitly in verification notes.

**When full-suite is mandatory**

- **Any backend logic or config changes:** Full backend pytest suite required.
- **Any persistence or path changes affecting `data/` or `out/`:** Full backend suite required.

**How to record exceptions**

- Must list failing test name(s), justification, and plan to fix in the next release.
- Must be time-boxed to the next release (no open-ended skips).

---

## 2. Recording outputs in `out/verification/<Release>/notes.md`

- **Path:** `out/verification/<Release>/notes.md` (e.g. `out/verification/R24.1/notes.md`).
- **Required content:**
  1. **Backend:** Paste the **tail** of the pytest run (last 5–10 lines showing "X passed, Y skipped" and duration).
  2. **Frontend tests:** Paste the **tail** of `npm run test -- --run` (test file summary and "X passed, Y skipped").
  3. **Frontend build:** Paste the **tail** of `npm run build` (success line and duration).
  4. **UAT checklist:** Section with checkboxes (e.g. `- [ ] Description of UAT step`); fill in or leave for manual run.

**Template snippet:**

```markdown
# <Release> Verification

## Gate outputs

### Backend tests
\`\`\`
cd chakraops; python -m pytest -v --tb=short
\`\`\`
**Result (tail):**
\`\`\`
(paste last 5–10 lines)
\`\`\`

### Frontend tests
\`\`\`
cd frontend; npm run test -- --run
\`\`\`
**Result (tail):**
\`\`\`
(paste last 5–10 lines)
\`\`\`

### Frontend build
\`\`\`
cd frontend; npm run build
\`\`\`
**Result:**
\`\`\`
(paste last 3–5 lines)
\`\`\`

---

## UAT checklist
- [ ] (item 1)
- [ ] (item 2)
```

- **Optional:** Add `api_samples/` or `E2E_VALIDATION_REPORT.md` under `out/verification/<Release>/` if the release defines them.

---

## 3. UAT: what to do and what to keep

### 3.1 What to do

- Execute the UAT checklist items listed in the release requirements or in `out/verification/<Release>/notes.md`.
- For each item: perform the step (e.g. "Run eval; verify Action Needed card"); check the box if done; note any failure or skip.

### 3.2 What screenshots/logs to keep

- **Screenshots (optional but recommended):** Dashboard Action Needed; Symbol page (Options/Shares) with next action and sizing; Notifications list; any new UI.
- **Logs:** If a gate or UAT step fails, keep the relevant terminal output or error message in the verification notes or in a short "UAT_issues" section.
- **Where:** In `out/verification/<Release>/` (e.g. `notes.md` for text; optional `screenshots/` if needed; do not commit secrets or PII).

### 3.3 Definition of "UAT done"

- All checklist items either checked (done) or explicitly marked "skipped" with reason.
- No unchecked critical item without reason; release owner signs off in notes (e.g. "UAT completed by <name/date>").

---

## 4. Rollback expectations

- **Code rollback:** Revert the release merge (or revert commits); redeploy. No special rollback script required unless the release introduced migrations or out/ layout changes.
- **Data rollback:** Decision artifact and `out/` are overwritten by the next eval or run; no automatic "restore previous artifact" — ensure backups or retention if needed (see CLEANUP_POLICY and retention docs).
- **Config rollback:** If release added env or config, document the previous value; rollback = restore previous config and redeploy.
- **Verification:** After rollback, run the same three gates to confirm environment is stable.

---

## 5. Definition of Done (template)

A release is **DONE** when all of the following are true:

- [ ] **Scope:** All features and fixes in the release requirements are implemented (or explicitly deferred with note in release notes).
- [ ] **Backend tests:** `cd chakraops && python -m pytest -v --tb=short` — **passed** (or documented skips).
- [ ] **Frontend tests:** `cd frontend && npm run test -- --run` — **passed** (or documented skips).
- [ ] **Frontend build:** `cd frontend && npm run build` — **passed**.
- [ ] **Verification:** `out/verification/<Release>/notes.md` exists and contains pasted gate outputs (tail) and UAT checklist.
- [ ] **Release notes:** `chakraops/docs/releases/<Release>_release_notes.md` (or repo-level `docs/releases/` if used) exists and describes scope, changes, and any known limitations.
- [ ] **Checklist:** RELEASE_CHECKLIST.md has the release section updated and all items checked or explicitly deferred.
- [ ] **UAT:** UAT checklist in verification notes completed or skipped with reason; no critical open issue.
- [ ] **Non-negotiables:** Decision artifacts remain code-only; no raw FAIL_/WARN_ in UI; no secrets in repo; `out/` hygiene respected.

---

*Use this playbook for every release. Keep verification notes in `out/verification/<Release>/notes.md` as the single place for gate evidence and UAT.*
