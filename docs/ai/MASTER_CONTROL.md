# ChakraOps AI Master Control

This file is the universal router for ChatGPT, Cursor, Claude Code, Codex, Claude Cowork, and the human operator.

## Root authority

Before acting, every tool must read:

1. `AGENTS.md`
2. `docs/ai/MASTER_CONTROL.md`
3. `docs/ai/PROGRAM_STATUS.md`
4. `docs/ai/PROGRAM_MASTER_PLAN.md`
5. `docs/ai/releases/<Release>/RELEASE_PACKET.md`
6. Its role-specific file inside that release folder

`AGENTS.md` is authoritative. This library may add controls, but it may not weaken root safety, gate, evidence, or release requirements.

## Workflow mode

Default: **SINGLE_OPERATOR_MAINLINE_LOOP_MODE** (see `AGENTS.md`).

- Work on synchronized `main`; push only after acceptance green.
- PR transport only if branch protection blocks direct push.
- Master program requirements: `docs/ai/MASTER_PROGRAM_R36_3_R40_REQUIREMENTS.md`.

## Universal launch keywords

The operator may use these short commands:

- `PROGRAM STATUS`
- `VALIDATE PROGRAM LIBRARY`
- `START <Release>`
- `CURSOR BUILD <Release>`
- `CLAUDE REVIEW <Release>`
- `CODEX REVIEW <Release>`
- `COWORK UAT <Release>`
- `READY FOR PR <Release>` (fallback when mainline push blocked)
- `RECORD MERGE <Release>`
- `NEXT RELEASE`
- `MASTER PROGRAM R36.3-R40` (continuous acceptance loop through R40)

## Tool behavior

When a launch keyword is received:

1. Resolve `<Release>`.
2. Read the root authority files.
3. Read the release packet.
4. Read the role file.
5. Verify repository root, branch, status, and allowed paths.
6. Perform only the permitted action.
7. Stop at the release packet's stop point.
8. Return a concise STEP report.

## One-writer rule

Only one writing agent may modify the working tree at a time.

Default writing agent: Cursor.

Claude Code, Codex, and Cowork are read-only unless a release packet explicitly grants a narrow writing role. Read-only reviewers return reports; Cursor or the operator records their verdicts in `STATUS.md` and `TOOL_LOG.md`.

## Locked product rules

- Manual trade execution only.
- No broker order routing.
- No autonomous trading.
- Brokerage integration, when approved later, is read-only.
- ORATS remains the sole active options-data provider unless the operator changes the charter.
- No silent fallback data.
- Stay in cash is a valid decision.
- Decision output should prioritize the top 5–7 actions.
