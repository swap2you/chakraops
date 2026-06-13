# ChakraOps Agent Contract

## Authority

- Human operator is the final authority.
- Agents stop and ask when scope is ambiguous.
- No agent may override operator instructions.

## Tool Roles

- **ChatGPT:** roadmap, product architecture, risk governance, release sequencing.
- **Claude Code:** architecture planning, repository audit, review.
- **Claude Cowork:** persistent coordination, documentation review, browser-assisted UAT.
- **Cursor:** approved implementation only, test execution, STEP reports.
- **Codex:** independent diff review, test-gap review, second opinion.

## Release Workflow

- One release = one branch: `release/Rxx.y`
- PR required before merge to main.
- No direct push to main.
- Tag required after merge: `chakraops-r<x>.<y>.<z>`
- Human operator approves merge and tags.
- Only one writing agent edits a branch at a time.

## Trading Safety

- Manual execution only.
- No broker order routing.
- No brokerage integration until explicitly approved later.
- ORATS is the sole active market-data provider.
- No silent provider fallback.
- Stay in cash is a valid outcome.

## Artifact Safety

- Decision artifacts remain code-only.
- Never persist prose or UI labels in decision artifacts.
- Never expose raw `FAIL_`, `WARN_`, or `PASS` labels in UI-facing output.
- Do not commit runtime files under `out/` or `data/`.
- Existing tracked `out/` files are known debt and must not be modified unless explicitly scoped.

## Required Gates

- Backend: `cd chakraops && python -m pytest tests -q --tb=short`
- Frontend tests: `cd frontend && npm run test -- --run`
- Frontend build: `cd frontend && npm run build`
- Record evidence locally in `out/verification/<Release>/notes.md`
- Stop if any gate fails.

## Forbidden Unless Explicitly Approved

- Force push
- History rewrite
- Schema migrations
- Runtime-file untracking
- Folder moves
- Broker integration
- New schedulers
- Deployment changes

## Tool-Specific Files

- Claude Code reads `CLAUDE.md`
- Cursor reads `.cursor/rules/chakraops.mdc`
- All tools treat `AGENTS.md` as the primary contract
