# Tool Router

## ChatGPT

Keyword: `PROGRAM STATUS` or `NEXT RELEASE`

Read:
- `docs/ai/PROGRAM_MASTER_PLAN.md`
- `docs/ai/PROGRAM_STATUS.md`
- release packet and status

Role:
- roadmap, risk, release sequencing, scope decisions, trade-off decisions

## Cursor

Keyword: `CURSOR BUILD <Release>`

Read:
- `AGENTS.md`
- `docs/ai/MASTER_CONTROL.md`
- release packet
- `cursor_build.md`

Role:
- sole default writing agent
- implementation, tests, evidence, STEP report
- stop before commit unless release packet authorizes release preparation

## Claude Code

Keyword: `CLAUDE REVIEW <Release>`

Read:
- release packet
- `claude_review.md`

Role:
- read-only architecture, design, coupling, risk, and completeness review

## Codex

Keyword: `CODEX REVIEW <Release>`

Read:
- release packet
- `codex_review.md`

Role:
- read-only independent diff, test, scope, safety, and regression review

## Claude Cowork

Keyword: `COWORK UAT <Release>`

Read:
- release packet
- `cowork_uat.md`

Role:
- browser/UAT coordination, screenshots, workflow verification, operator-facing usability review

## Operator

Keywords:
- `READY FOR PR <Release>`
- `RECORD MERGE <Release>`

Role:
- final approval, PR merge, tag approval, production-use decision
