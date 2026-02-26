# Docs archive

**Purpose:** Hold superseded design docs, legacy phase plans, and one-off audit reports. No release notes or verification notes are archived here; those stay in `chakraops/docs/releases/` and `out/verification/<Release>/`.

**R24.7.1:** Archive pass completed. All candidates from REPO_ARCHITECTURE_MAP were moved (git mv); see [INDEX.md](./INDEX.md) for old path → new path and justification.

---

## Structure

| Subfolder | Contents |
|-----------|----------|
| `phase_plans/` | Legacy phase plans (phase4_plan, PHASE_8_PLAN, phase4_eligibility, PHASE_10_PORTFOLIO_COMPLETION, PHASE_12_FILL_WORKFLOW). |
| `audits/` | One-off audit and fix reports (DELTA_GATE_FIX_SUMMARY, FRONTEND_BACKEND_WIRING_AUDIT, TEST_HYGIENE_INTEGRITY_AUDIT, AUDIT_REPORT). |
| `superseded/` | Other superseded docs (phase0_keep_list, project_status_bookmark_through_R22_7). |
| `releases_supporting_artifacts/` | Duplicate verification/gate-output docs (R24.2–R24.5); canonical evidence in out/verification/<Release>/notes.md. |
