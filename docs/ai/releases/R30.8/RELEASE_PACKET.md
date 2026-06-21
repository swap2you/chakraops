# RELEASE_PACKET — R30.8

## Release

R30.8

## Branch

release/R30.8

## Objective

Create a repo-native AI operating library so future releases use short launch commands, release packets, shared status files, and tool logs instead of giant copied prompts.

## Risk Level

Level 1 — docs/governance

---

## Scope

- Create `docs/ai/` operating model library (README, OPERATING_MODEL, REVIEW_POLICY, QUICK_COMMANDS, RELEASE_TRAVELER, WORKFLOW_STATE_TEMPLATE)
- Create `docs/ai/prompts/` library (prompts 00–06)
- Create `docs/ai/releases/` framework (README, TEMPLATE_RELEASE_PACKET)
- Create R30.8 release folder (`docs/ai/releases/R30.8/`)
- Create R31.0 starter packet (`docs/ai/releases/R31.0/`)
- Update `docs/master/CURRENT_STATE.md`
- Update `chakraops/docs/releases/RELEASE_CHECKLIST.md` with R30.8 block
- Create `chakraops/docs/releases/R30.8_requirements.md`
- Create `chakraops/docs/releases/R30.8_release_notes.md`

## Non-Goals

- No code changes
- No test changes
- No frontend source changes
- No backend source changes
- No runtime changes
- No GitHub Actions changes
- No deployment changes
- No trading logic changes
- No broker integration
- No database changes
- No scheduler changes

## Allowed Files

- `docs/ai/**`
- `docs/master/CURRENT_STATE.md`
- `chakraops/docs/releases/RELEASE_CHECKLIST.md`
- `chakraops/docs/releases/R30.8_requirements.md`
- `chakraops/docs/releases/R30.8_release_notes.md`

## Forbidden Files

- All source files under `chakraops/app/`
- All source files under `frontend/src/`
- All test files under `chakraops/tests/`
- `out/`
- `data/`
- GitHub Actions under `.github/`
- All other existing documentation not listed above

---

## Implementation Steps

1. Verify branch and clean working tree.
2. Create `docs/ai/` core library files (6 files).
3. Create `docs/ai/prompts/` (7 files).
4. Create `docs/ai/releases/` framework (2 files).
5. Create `docs/ai/releases/R30.8/` folder (7 files: RELEASE_PACKET, STATUS, TOOL_LOG, cursor_build, claude_review, codex_review, pr_description).
6. Create `docs/ai/releases/R31.0/` starter folder (7 files).
7. Update `docs/master/CURRENT_STATE.md`.
8. Update `chakraops/docs/releases/RELEASE_CHECKLIST.md`.
9. Create `chakraops/docs/releases/R30.8_requirements.md`.
10. Create `chakraops/docs/releases/R30.8_release_notes.md`.

## Verification Gates

`AGENTS.md` baseline gates are mandatory before DONE at every risk level. This release adds no trading or UAT gates, but all three baseline gates are required:

- [ ] Backend: `cd chakraops && python -m pytest tests -q --tb=short`
- [ ] Frontend tests: `cd frontend && npm run test -- --run`
- [ ] Frontend build: `cd frontend && npm run build`
- [ ] Git diff operator spot-check: no source/runtime files changed
- [ ] Verification evidence: `out/verification/R30.8/notes.md`

## Review Requirements

- Cursor: required
- Claude Code: not required (Level 1)
- Codex: required (independent diff/scope review)

---

## PR Title

R30.8 — AI operating library + release traveler

## Rollback

Rollback tag: `chakraops-r30.7.0`

Steps:
1. Delete the `docs/ai/` directory.
2. Remove the R30.8 block from `chakraops/docs/releases/RELEASE_CHECKLIST.md`.
3. Delete `chakraops/docs/releases/R30.8_requirements.md` and `R30.8_release_notes.md`.
4. Revert `docs/master/CURRENT_STATE.md` to R30.7 state.

---

## Stop Point

Cursor stops before commit. Operator reviews, then instructs commit, push, PR.
