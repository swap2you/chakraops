# Known Issues — ChakraOps

_Last updated: R30.6 documentation baseline_

---

## 1. Nested Repository Path Ambiguity

**Issue:** The workspace has a nested path pattern (`chakraops/chakraops/`) that has caused verification evidence and release notes to land in inconsistent locations across releases.

**Impact:** Some verification paths in `RELEASE_CHECKLIST.md` reference `chakraops/chakraops/out/verification/` while others reference `out/verification/`. Agents may write evidence to the wrong path.

**Current handling:** Canonical path is `out/verification/<Release>/notes.md` from the repo root. Duplicate paths are acknowledged in the checklist.

**Future cleanup required:** Audit all checklist entries and normalize paths. Coordinate with operator before any folder moves.

---

## 2. Duplicate Release Documentation Trees

**Issue:** Two release documentation directories exist: `docs/releases/` (legacy) and `chakraops/docs/releases/` (current ledger). Both contain release notes for overlapping release ranges.

**Impact:** Agents reading the wrong tree may reference stale or superseded information.

**Current handling:** `chakraops/docs/releases/` is the authoritative ledger. `docs/releases/` is legacy reference only; do not write there.

**Future cleanup required:** Mark `docs/releases/` clearly as archived. Consider a single redirect file.

---

## 3. Verification Path Drift

**Issue:** Verification evidence paths (`out/verification/<Release>/notes.md`) have drifted across releases due to the nested-repo ambiguity and operator-directed path choices.

**Impact:** Checklist entries may point to paths that do not exist or are in unexpected locations.

**Current handling:** Accepted as known debt. Evidence is present even if paths vary.

**Future cleanup required:** Audit and standardize all `out/verification/` references in `RELEASE_CHECKLIST.md`.

---

## 4. Tracked Runtime Files Under `out/`

**Issue:** Several runtime output files under `out/` are tracked in git (e.g., `out/decision_latest.json`, `out/mark_refresh_state.json`, `out/notifications.jsonl`).

**Impact:** Runtime state bleeds into version control. Diff noise. Risk of committing stale or sensitive runtime values.

**Current handling:** Treated as known debt. Files must not be modified unless the release explicitly scopes runtime-file hygiene cleanup.

**Future cleanup required:** Untrack runtime files in a dedicated hygiene release. Update `.gitignore` accordingly. Requires operator explicit approval.

---

## 5. React Nested `<tr>` Warnings

**Issue:** Frontend emits React warnings about invalid DOM nesting (`<tr>` inside `<tr>` or similar table structure violations) during test runs and runtime.

**Impact:** Warning noise in test output and browser console. No functional breakage observed.

**Current handling:** Warnings are present but do not block gates. Skipped count stable at 18.

**Future cleanup required:** Identify the table components producing invalid nesting and fix DOM structure.

---

## 6. Vite Static/Dynamic Import Warnings

**Issue:** Vite emits warnings about mixed static and dynamic imports or chunk-size thresholds during `npm run build`.

**Impact:** Build succeeds but warning output may obscure real errors.

**Current handling:** Build passes. Warnings accepted as known noise.

**Future cleanup required:** Review import patterns and consider explicit dynamic-import boundaries or `manualChunks` configuration.

---

## 7. Frontend Bundle-Size Warning

**Issue:** `npm run build` reports one or more chunks exceeding the recommended size limit.

**Impact:** Performance advisory only. No functional breakage.

**Current handling:** Accepted. Build gate passes.

**Future cleanup required:** Profile bundle, apply code splitting or lazy loading where appropriate.

---

## 8. Stale Roadmap Trackers

**Issue:** `docs/master/` contains roadmap and phase-status documents that have not been updated since earlier phases (R21–R25 era).

**Impact:** Agents reading stale roadmap docs may produce incorrect release sequencing recommendations.

**Current handling:** `CURRENT_STATE.md` and `SOURCE_OF_TRUTH.md` supersede stale trackers.

**Future cleanup required:** Refresh or archive `ROADMAP_2026.md` and `PHASE_STATUS.md` in a dedicated documentation tracker refresh release.

---

## 9. R30 Local Evidence Path Gap

**Issue:** Some `RELEASE_CHECKLIST.md` R30.x entries reference verification paths under `chakraops/chakraops/out/verification/` rather than the canonical root path `out/verification/`. The R30.0 entry is one example.

**Impact:** Evidence traceability gap for individual R30.x releases if the nested path does not exist at the repo root.

**Current handling:** Acknowledged. R30 changes (R30.0–R30.5) are merged into `main` and represented by tag `chakraops-r30.5.0`. There is no dedicated R30.0 tag. No rework planned.

**Future cleanup required:** Confirm paths exist; add a note or redirect if not.

---

## 10. Cowork Linux-Mount Unlink Limitations

**Issue:** Claude Cowork running in a Linux-mount environment may be unable to unlink or overwrite certain files due to mount permissions or Windows filesystem lock behavior.

**Impact:** Cowork may silently skip file writes or produce partial edits without error.

**Current handling:** Operator verifies Cowork output independently. Cursor is used for all file writes requiring reliability.

**Future cleanup required:** Document Cowork environment constraints. Prefer Cursor for any write that must be verified.
