# R35.1 — Authorized Paths (exact, no wildcards)

**Release ID:** R35.1 · **Branch:** `release/R35.1-dedicated-ports-stabilization` · **Base:** `2c1393f`

Authorization takes effect **only after** the documentation-only authorization commit (`docs(r35.1): authorize dedicated-port stabilization`). No directory wildcards, globs, "related files", or "as needed" scope is granted.

---

## Reconciled Git inventory (authoritative)

- **Modified tracked files: 28** (from `git status --porcelain=v1` / `git diff --name-only`).
- **Untracked implementation/test files: 3**.
- **Local-only (never commit): 1** — `frontend/.env.development`.
- **Unrelated (excluded from R35.1): 1** — `ChakraOps_Post_R35_R36_Prompt_Library.md`.

The Phase 0 executive summary said "24 modified"; the authoritative Git count is **28** (matching the Phase 0 diffstat "28 files changed"). Discrepancy resolved in favor of **28**.

---

## A. Authorized — pre-existing modified tracked paths (28)

1. `.gitignore` — **only** to restore the rule that keeps `frontend/.env.development` ignored (must remove any `!frontend/.env.development` un-ignore).
2. `chakraops/app/api/server.py`
3. `chakraops/app/core/operations/process_ownership.py`
4. `chakraops/docs/RUNBOOK_EXECUTION.md`
5. `chakraops/docs/RUNBOOK_MARKET_LIVE.md`
6. `chakraops/docs/RUNBOOK_PROMPT.md`
7. `chakraops/docs/RUNBOOK_SCHEDULER_OPERATIONS.md`
8. `chakraops/docs/RUNBOOK_STARTUP_SHUTDOWN.md`
9. `chakraops/docs/RUNBOOK_TROUBLESHOOTING.md`
10. `chakraops/docs/VALIDATION_PLAYBOOK.md`
11. `chakraops/docs/debug_data_completeness.md`
12. `chakraops/scripts/market_live_validation.py`
13. `chakraops/scripts/run_api.py`
14. `chakraops/scripts/sanity_one_pipeline.py`
15. `chakraops/scripts/validate_hd_delta_and_reasons.py`
16. `chakraops/scripts/validate_one_symbol.py`
17. `docker-compose.yml`
18. `docs/master/RUNBOOK_DEV_EXECUTION.md`
19. `frontend/.env.example`
20. `frontend/README.md`
21. `frontend/src/pages/AnalyticsPage.tsx`
22. `frontend/src/pages/StrategyPage.tsx`
23. `frontend/vite.config.js`
24. `frontend/vite.config.ts`
25. `scripts/chakraops_common.ps1`
26. `scripts/health_check_chakraops.ps1`
27. `scripts/run_r31_r35_live_smoke.ps1`
28. `scripts/start_chakraops.ps1`

## B. Authorized — untracked source-of-truth and test files (3)

29. `scripts/chakraops_ports.ps1`
30. `chakraops/app/core/chakraops_ports.py`
31. `chakraops/tests/test_chakraops_ports.py`

## C. Authorized — conditional Phase 2 path (1)

32. `frontend/src/test/liveEndpoints.e2e.test.ts` — **only** to update the stale `localhost:8000` instructional comment. Currently unmodified; authorized as a net-new edit in Phase 2.

## D. Authorized — governance/validation docs (this commit + Phase 3 evidence)

- `docs/ai/releases/R35.1/R35_1_SCOPE.md`
- `docs/ai/releases/R35.1/R35_1_DESIGN.md`
- `docs/ai/releases/R35.1/R35_1_RISK_REGISTER.md`
- `docs/ai/releases/R35.1/R35_1_ACCEPTANCE_CRITERIA.md`
- `docs/ai/releases/R35.1/R35_1_AUTHORIZED_PATHS.md`
- `docs/ai/releases/R35.1/R35_1_NON_RETROACTIVE_WAIVER.md`
- `docs/ai/validation/R35_1_ACCEPTANCE_MANIFEST.json`
- `docs/ai/validation/R35_1_SELF_REVIEW_CHECKLIST.md`
- `out/verification/R35.1/notes.md` — evidence (local; `out/` is git-ignored, not committed)

---

## Forbidden paths / actions (exact)

- `frontend/.env.development` — **never commit** (local-only).
- `ChakraOps_Post_R35_R36_Prompt_Library.md` — unrelated; never stage/commit in R35.1.
- `.env` — never commit.
- `.env.*` — never commit **except** the explicitly named tracked template `frontend/.env.example`.
- Strategy thresholds — forbidden.
- Recommendation rules unrelated to ports — forbidden.
- Scheduler activation — forbidden.
- Recurring-job activation — forbidden.
- Robinhood integration — forbidden.
- Broker or order endpoints — forbidden.
- Broad Ruff cleanup — forbidden.
- Unrelated UI redesign — forbidden.
- R36 Universe or strategy implementation — forbidden.
