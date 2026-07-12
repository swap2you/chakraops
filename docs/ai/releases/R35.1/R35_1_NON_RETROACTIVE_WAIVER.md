# R35.1 — Non-Retroactive Waiver

**Release ID:** R35.1
**Branch:** `release/R35.1-dedicated-ports-stabilization`
**Base SHA:** `2c1393ff31bf579708d8388e3a48d2092305a497`
**Authorization commit SHA:** _(placeholder — the documentation-only commit that carries this waiver)_

---

## Statement of fact

- R31–R35 were previously validated and merged to `main` (PR #15, merge `2c1393f`).
- A dedicated-port patch (backend `18800`, frontend `18873`) was created **unintentionally in the dirty working tree of `main`** while debugging a UI "Failed to load universe" error.
- **No patch changes were committed or pushed from `main`.** Local `main` still equals `origin/main` at `2c1393f`.
- The work was recovered onto `release/R35.1-dedicated-ports-stabilization` via `git switch -c`, **preserving the working tree** and **without rewriting history**.

## Scope of this waiver

This waiver is **narrow** and **non-retroactive**:

1. It authorizes **future** edits to the exact paths listed in `R35_1_AUTHORIZED_PATHS.md`, and **only** after this documentation-only authorization commit.
2. It does **not** claim, imply, or pretend that the pre-existing uncommitted edits were pre-authorized. They were not. They were produced ad hoc during debugging and are being brought under governance now.
3. It does **not** cover any path outside the authorized list.
4. It does **not** waive any safety control.

## Pre-existing uncommitted paths covered (brought under governance)

The 28 modified tracked files + 3 untracked implementation/test files enumerated in `R35_1_AUTHORIZED_PATHS.md` sections A and B are the pre-existing uncommitted work now covered by this waiver for **continued** (Phase 2) work.

## Safety affirmations (unchanged)

- Scheduler and recurring jobs remain **DISABLED**.
- Trading remains **manual-only**; `trade_execution=false`; **no broker-write** capability.
- No strategy thresholds or recommendation rules are changed.
- No `.env` file is committed; `frontend/.env.development` stays local-only.
- Secrets are never printed; evidence is redacted.
- Canonical checkout only; obsolete `C:\Development\Workspace\ChakraOps` is not used.

## Authorization gate

Further implementation (Phase 2) and validation (Phase 3) are authorized **only** after the commit:

`docs(r35.1): authorize dedicated-port stabilization`
