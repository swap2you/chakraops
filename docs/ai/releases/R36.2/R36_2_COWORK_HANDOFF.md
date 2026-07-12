# R36.2 — Cowork UAT Handoff

## Preconditions
- On validated `main` containing the R36.2 merge.
- Backend 18800, frontend 18873. Start via `scripts/start_chakraops.ps1`.
- If no Universe V2 snapshot exists yet, POST `/api/ui/universe-v2/refresh` once (manual,
  in-process; no scheduler) after an evaluation has run, or verify the read endpoints
  report a fail-closed "no snapshot" state cleanly.

## What to verify in the browser (http://127.0.0.1:18873)
1. Universe page loads within a few seconds (no 30–60s spinner) — authoritative read is the
   published snapshot.
2. Universe V2 panel shows: research-pool count, lifecycle funnel (ADMITTED/WATCH/
   QUARANTINE/REMOVED), per-strategy eligible counts (CORE/BALANCED/AGGRESSIVE_WHEEL/SHARES),
   snapshot version + freshness, top rejection reasons.
3. Universe rows show a human reason (no empty "Reason" cell, no raw `FAIL_`/`WARN_`),
   with safety-critical reasons ranked above soft reasons.
4. Symbol Diagnostics shows the symbol's lifecycle state + per-strategy membership.
5. A quarantined symbol (stale/missing data) is never shown as eligible for any strategy.
6. Console has no errors; no network request goes to port 8000/5173.

## Notes
- Advisory-only; no trading actions exist. Stay-in-cash remains valid.
- Report any symbol whose lifecycle/membership looks wrong with the measured value +
  threshold shown in the reason (for calibration in a later release).
