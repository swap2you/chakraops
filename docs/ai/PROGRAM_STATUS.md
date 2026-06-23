# ChakraOps Program Status

Last initialized: 2026-06-21
Last updated: 2026-06-23 (R34.0 COMPLETE — implementation and technical validation complete; backend 1224/3; frontend 334/18; build PASS; **H-5 CLOSED**. Claude closure **APPROVED WITH NON-BLOCKING NOTES**; Codex closure **BLOCKED only on authorization ordering** — operator waiver recorded for `2c41ba2`/`test_r340_refresh_lock_ownership.py`; final Codex governance confirmation pending before R35.0)

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
| R34.0 | COMPLETE — implementation and technical validation complete (backend 1224/3; frontend 334/18; build PASS; secret scan 0 hits): transaction-safe refresh, OS-native lock, complete ORATS provider redaction, live sector enforcement, rendered canonical cutover, frontend correctness. **H-5 CLOSED**. Claude closure **APPROVED WITH NON-BLOCKING NOTES**; Codex closure **BLOCKED only on authorization ordering** (operator waiver `2c41ba2` recorded) | Cursor / Claude / Codex | Final Codex governance closure, then R35.0 |
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
