# Current State — ChakraOps

_Last updated: 2026-08-10 — master program R36.3–R40 start; baseline `63d83d00e3ceb9ac15a080a54178adf0d7e78267`_

## Release Status

| Field | Value |
|-------|-------|
| Latest merged on main | R36.2 (Universe V2) + post-merge scheduler/UI polish |
| Baseline SHA | `63d83d00e3ceb9ac15a080a54178adf0d7e78267` |
| Current branch | `main` |
| Current mode | `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` |
| Active milestone | R36.3 — Whole-Application Trust & Wiring Stabilization |
| Requirements | `docs/ai/MASTER_PROGRAM_R36_3_R40_REQUIREMENTS.md` |

## Ports

| Service | Port |
|---------|------|
| Backend | http://127.0.0.1:18800 |
| Frontend | http://127.0.0.1:18873 |

## Trading Safety

Manual execution only. No auto-trading. No broker order routing. ORATS is the sole active market-data provider. No silent provider fallback. Stay in cash is a valid outcome. Schedules remain disabled.

## Program

R36.3 → R37 → R38 → R39 → R40 (closes master program). See `docs/ai/PROGRAM_STATUS.md`.
