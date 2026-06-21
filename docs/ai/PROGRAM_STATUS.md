# ChakraOps Program Status

Last initialized: 2026-06-21
Last updated: 2026-06-21 (R33 governance corrected; R34.0 canonical live cutover complete + gate-verified; H-5 resolved at API/data layer; product Phases 4–9 staged)

## Program branch and workflow

- Single program branch: `release/R31-R35-program`.
- R31–R35 are sequential milestones on this one branch, not separate PR branches.
- One milestone commit per completed milestone (five milestone commits total).
- One final PR opened only after R35.0 is complete. No merge or tag without operator approval.
- Cursor is the only writing agent. Claude Code and Codex are read-only reviewers.

| Release | Status | Owner | Next action |
|---|---|---|---|
| R31.0 | IMPLEMENTED (gates green, committed; awaiting review) | Cursor / Claude / Codex | Operator review of audit + blueprint; resolve D-1 (R30.8) |
| R32.0 | COMPLETE — C-1 + Claude notes + full data-reliability scope delivered and gate-verified; Claude APPROVED-WITH-NOTES (notes closed in 049cb2f); Codex review PENDING (quota) | Cursor / Claude / Codex | Deferred Codex R32 review |
| R33.0 | IMPLEMENTED + TESTED, Claude **BLOCKED** on live cutover — canonical engine is correct/tested but not yet the authoritative live recommendation path; H-5 OPEN, reassigned to R34 | Cursor / Claude / Codex | Closed by R34 live cutover; deferred Codex review |
| R34.0 | CUTOVER COMPLETE (gate-verified) — canonical engine is the authoritative live recommendation at API/data layer (H-5 resolved there); capital-set safety + persistence decision (RETAIN) done. Product Phases 4–9 (dashboard/nav/portfolio/universe/backtest/journal/reports/frontend) STAGED, not claimed complete | Cursor / Claude / Codex | Claude re-review + Cowork UAT + deferred Codex; then staged product phases / R35 |
| R35.0 | PACKET_READY / DEPENDS_ON_R34 | Cursor / Cowork | Wait for product-flow acceptance |

## Current program rule

Only one release may be `ACTIVE` unless the operator explicitly authorizes parallel read-only work. Milestones advance only when the previous milestone is green and its dependency (prior approved output) is satisfied.

## Status values

`READY_TO_START`, `ACTIVE`, `BLOCKED`, `IMPLEMENTED`, `REVIEWED`, `VALIDATED`, `UAT_PASS`, `PR_READY`, `MERGED`, `TAGGED`, `DEFERRED`.

## Common tracking

Each release folder contains:

- `RELEASE_PACKET.md`
- `STATUS.md`
- `TOOL_LOG.md`
- `cursor_build.md`
- `claude_review.md`
- `codex_review.md`
- `cowork_uat.md`
- `pr_description.md`

Read-only reviewers do not edit these files. Cursor or the operator records verdicts after review.
