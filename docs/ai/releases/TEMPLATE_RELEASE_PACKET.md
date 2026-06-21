# RELEASE_PACKET — <Release>

_Copy this file to `docs/ai/releases/<Release>/RELEASE_PACKET.md` and fill in all fields before starting the release._

---

## Release

<!-- e.g. R31.0 -->

## Branch

<!-- e.g. release/R31.0 -->

## Objective

<!-- One sentence. -->

## Risk Level

<!-- Level 0 / 1 / 2 / 3 / 4 — see docs/ai/REVIEW_POLICY.md -->

---

## Scope

<!-- Bullet list of exactly what will change. Be specific. -->

-

## Non-Goals

<!-- What is explicitly out of scope. Every reader must understand what is forbidden. -->

- No trading logic changes
- No ORATS changes
- No database schema changes
- No scheduler changes
- No GitHub Actions changes
- No brokerage integration
- No deployment changes
- No Git-history rewrite
- No runtime files under `out/` or `data/`

## Allowed Files

<!-- List every file path or glob allowed to change. Tools must not touch anything else. -->

-

## Forbidden Files

<!-- List files or paths that must not change. -->

- `out/`
- `data/`
- All test files (unless test changes are explicitly in scope)
- All backend source (unless backend changes are explicitly in scope)
- All frontend source (unless frontend changes are explicitly in scope)

---

## Implementation Steps

<!-- Ordered steps for Cursor. -->

1.
2.
3.

## Verification Gates

<!-- Which gates are required. Check all that apply. -->
<!-- IMPORTANT: Documentation-only releases still require the baseline release gates and evidence required by AGENTS.md before DONE. Git diff review is an additional scope check, not a replacement for backend/frontend/build gates. -->

- [ ] Backend: `cd chakraops && python -m pytest tests -q --tb=short`
- [ ] Frontend tests: `cd frontend && npm run test -- --run`
- [ ] Frontend build: `cd frontend && npm run build`
- [ ] Git diff scope check: only Allowed Files changed; no source/runtime files modified
- [ ] Manual UAT: `out/verification/<Release>/notes.md` (required for Level 3+; optional for Level 1–2 unless operator adds it)
- [ ] Evidence: `out/verification/<Release>/notes.md`

## Review Requirements

<!-- Per docs/ai/REVIEW_POLICY.md -->

- Cursor: required
- Claude Code: <!-- required / not required / optional -->
- Codex: <!-- required / not required -->

---

## PR Title

<!-- e.g. R31.0 — Repository and product baseline audit -->

## PR Description

<!-- Link to docs/ai/releases/<Release>/pr_description.md -->

## Rollback

<!-- Previous stable tag. Steps to revert. -->

Rollback tag: <!-- e.g. chakraops-r30.8.0 -->

Steps:
1.
2.

---

## Status-Log Instructions

Cursor updates `docs/ai/releases/<Release>/STATUS.md` after each implementation phase. Read-only reviewers (Claude Code, Codex) do not update STATUS.md.

## Tool-Log Instructions

Cursor adds a dated entry to `docs/ai/releases/<Release>/TOOL_LOG.md` after implementation. Read-only reviewers do not update TOOL_LOG.md — they return their verdict, and the operator or a subsequent recording step copies it in.

## Stop Point

<!-- Define the explicit stop point for each tool. -->

Cursor stops before commit unless operator explicitly instructs otherwise.
