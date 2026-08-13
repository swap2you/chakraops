# R70.1 Final Closure — Remediation Candidate

**Status:** R70_1_REMEDIATED_PENDING_CURSOR_FULL_GATE_AND_INDEPENDENT_REVALIDATION
**Reviewed base:** `b898a5cd5f51858669845927c20479efd28cc252`
**Remediation range:** inspect `git log --oneline b898a5c..HEAD`; the published candidate may be connector-squashed
**Candidate SHA:** record `git rev-parse HEAD` in the external acceptance evidence
**Date:** 2026-08-13

The earlier Batch G closure is superseded. Independent revalidation found that
`offline_eval_proof.py` could target canonical `out` and request a LIVE
full-universe evaluation outside the coordinator. That was a HIGH-severity
one-authority violation and correctly produced **NO_GO**.

## R70.1 authority closure

- Canonical LIVE full-universe persistence now requires an internal,
  context-local coordinator capability.
- `offline_eval_proof.py` is a marked secondary evaluator, is PAPER-only, and
  rejects canonical `out` including resolved aliases.
- `run_and_save.py` documentation and examples are PAPER-only and use an
  isolated harness output directory.
- AST caller inventory and runtime guard tests fail closed if a new direct LIVE
  caller or canonical-output bypass appears.
- No broker write, scheduler enablement, live runtime output, or canonical data
  migration is part of this remediation.

## True full backend gate

Command:
```
OUT_DIR=<iso> DATA_DIR=<iso> .\.venv\Scripts\python.exe -m pytest tests -q --tb=line --junitxml=<iso>\backend-full-junit.xml
```

Codex result on Linux: **1762 passed, 6 skipped**, exit 0 (74.89s).

Focused authority result: **35 passed**, exit 0.

Ruff: `ruff check app tests` — exit 0.

## Frontend

- Pinned runtime: Node `20.11.1`.
- `npm ci`: exit 0; 405 packages installed on Linux after making the
  Windows-only Rollup binary optional.
- `npm run typecheck`: exit 0.
- `npm run build`: exit 0; 1511 modules transformed.
- `npm run test`: **Cursor evidence required**. In the Codex sandbox, Vitest
  reports passing test files but does not release Tinypool's final task, even
  for an unrelated one-line scratch test. A timeout is not an accepted pass.

## Cursor acceptance checkpoints

1. Record the exact candidate SHA and prove the worktree is clean.
2. Run the focused R70 authority batch and full isolated backend gate.
3. Run Ruff, clean `npm ci`, typecheck, full Vitest, and production build under
   Node 20.11.1. Vitest must terminate naturally with exit 0.
4. Prove canonical LIVE writes fail outside the coordinator and succeed only
   inside its capability scope; prove PAPER and isolated harness paths remain
   usable.
5. Prove canonical `out` and resolved aliases are refused by the offline CLI
   without changing canonical bytes.
6. Confirm no broker writes, scheduler enablement, canonical runtime-data
   mutation, deployment, or R71 work occurred.
7. Accept only when all evidence names the same immutable candidate SHA.

Do not claim R70 GO, merge, deploy, or start R71 until Cursor and the final
independent reviewer both accept the same candidate SHA.
