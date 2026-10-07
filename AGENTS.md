# ChakraOps Agent Contract

Canonical checkout: `C:\Users\swap2\NEEWA-Personal\projects\ChakraOps`.
Origin: `https://github.com/swap2you/chakraops.git` on `main`.
Operating contract: `docs/NEEWA.md`. Commands: `docs/OPERATIONS.md`.

## Authority

- Human operator is the final authority.
- Agents stop and ask when scope is ambiguous.
- No agent may override operator instructions.
- Only one writer edits this checkout at a time. Checkpoint and release any active child before mutating.

## Tool Roles

- **ChatGPT:** roadmap, product architecture, risk governance, release sequencing.
- **Claude Code:** architecture planning, repository audit, review.
- **Claude Cowork:** persistent coordination, documentation review, browser-assisted UAT.
- **Cursor:** implementation, test execution, and STEP reports. Use one model from the live Cursor agent inventory at a supported High or Extra High effort.
- **Codex:** read-only validation through ChatGPT sign-in (`codex login` / `codex exec`). Do not send this route through `OPENAI_API_KEY` or another paid API fallback.
- Completion is evidence: command exits, runtime SHA, and mission receipts. A note or registry row is not ownership.

## Release Workflow

### Default: SINGLE_OPERATOR_MAINLINE_LOOP_MODE

Owner-approved for this private single-operator repository (authorized 2026-08-10):

- Work directly on a clean synchronized `main` when local `main` == `origin/main` and the tree is clean at release start.
- No release branches unless technically required (migration isolation, parallel experiment, or branch protection forces it).
- No PR ceremony unless GitHub branch protection physically blocks direct pushes.
- Atomic, coherent commits; push `main` only after the current release’s acceptance contract is green locally.
- After push: verify local == `origin/main`, run focused post-push smoke, then continue to the next release automatically.
- Tag optional after release close: `chakraops-r<x>.<y>.<z>` when the operator requests tagging.
- Only one writing agent edits the tree at a time.

If branch protection blocks direct push, use the **minimum** PR transport required, then continue autonomously. Never force-push. Never rewrite history.

### Fallback: release-branch / PR mode

Use only when mainline mode is blocked or the operator explicitly requests it:

- One release = one branch: `release/Rxx.y`
- PR required before merge to main
- Tag after merge when requested
- Human operator approves merge and tags

## Trading Safety

- Manual execution only.
- No broker order routing.
- No brokerage write integration.
- Robinhood (when present) is hard read-only with write denylist.
- ORATS is the sole active market-data provider for options.
- No silent provider fallback.
- Stay in cash is a valid outcome.
- Broker execution and order routing stay disabled.
- Broker execution and order routing stay disabled.
- Recurring snapshots, overnight regression, and owner Slack notifications are authorized by `requirements/NEEWA_ChakraOps_Autonomous_Delivery_Charter.md` after this checkout is the sole writer. Do not revive a legacy cron with incorrect session assumptions. The GitHub market-health workflow stays manual.

## Artifact Safety

- Decision artifacts remain code-only.
- Never persist prose or UI labels in decision artifacts.
- Never expose raw `FAIL_`, `WARN_`, or `PASS` labels in UI-facing output.
- Do not commit runtime files under `out/` or `data/`.
- Existing tracked `out/` files are known debt and must not be modified unless explicitly scoped.
- Local-only `chakraOpsDropbox/` must remain untracked (`.git/info/exclude`).

## Required Gates

- Backend: `cd backend && python -m pytest tests -q --tb=short`
- Frontend tests: `cd frontend && npm run test -- --run`
- Frontend build: `cd frontend && npm run build`
- Record evidence locally in `out/verification/<Release>/notes.md`
- Stop the release only if a gate fails after remediation attempts and a genuine blocker remains (credentials, external provider, migration safety, repository protection, or unresolved owner policy).

## Forbidden Unless Explicitly Approved

- Force push
- History rewrite
- Schema migrations that risk data loss without a rollback plan
- Runtime-file untracking of known debt without scope
- Broker write / order execution
- Enabling broker or order execution on a schedule
- The 2026-10-07 cleanup directive authorizes the shallow layout and removal of proven duplicate checkouts after central main is verified. It does not authorize broker execution or recurring jobs.
- Deployment changes outside authorized release scope

## Tool-Specific Files

- Claude Code reads `CLAUDE.md`
- Cursor reads `.cursor/rules/chakraops.mdc`
- All tools treat `AGENTS.md` as the primary contract
