# ChakraOps — Operator Daily Runbook (R40)

**Audience:** Single operator, manual-only Wheel + Shares workflow.  
**Ports:** Backend **18800**, Frontend **18873**. Do not use 8000/5173 for ChakraOps.  
**Safety:** No auto trading. No broker order routing. Scheduler stays **off**. Stay in Cash is valid.

Related: [RUNBOOK_STARTUP_SHUTDOWN.md](RUNBOOK_STARTUP_SHUTDOWN.md), [RUNBOOK_TROUBLESHOOTING.md](RUNBOOK_TROUBLESHOOTING.md).

---

## 1. Start the stack

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\start_chakraops.ps1
```

Confirm:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/healthz" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:18873/" -UseBasicParsing
```

Open UI: **http://127.0.0.1:18873/**

---

## 2. Daily operator path

| Step | Where | What to do |
|------|--------|------------|
| 1 | **Command Center** (`/`) | Status, data health, actions today, Stay in Cash reason, alerts |
| 2 | **Opportunities** (`/opportunities`) | Review CSP / CC / Shares / Watch / Near Miss / Blocked |
| 3 | **Symbol** / **Wheel** | Deep-dive candidates; Wheel lifecycle when relevant |
| 4 | **Trade Ticket** (`/ticket`) | Build **manual** ticket only — execute in broker UI yourself |
| 5 | **Journal** | Record the fill after you trade |
| 6 | **Notifications** | Ack / archive; no raw FAIL/WARN expected |

Do **not** treat Near Miss or Blocked as approval. Quarantined symbols are not actionable.

---

## 3. Data health checklist

- Provider / market freshness acceptable (Command Center + System)
- Portfolio source trusted; note staleness if present
- Integrity / trust banners: remediate before sizing up
- If data is missing or stale → **Stay in Cash** / no new entries

---

## 4. Stay in Cash

Stay in Cash / no action is a first-class outcome. Prefer cash when:

- Regime or earnings blackout blocks entries
- Guardrails / cash buffer insufficient
- Data health degraded
- No recommendation scores above actionable threshold

---

## 5. Broker status NO_GO

If Robinhood / broker integration is **NO_GO** or read-only unavailable:

- Continue with **manual portfolio** entry and trusted snapshot discipline
- Do **not** invent live balances
- Do **not** enable broker writes

---

## 6. Scheduler

Scheduler remains **disabled** unless an explicit operator-approved env flag is set for a controlled session. Feature releases must not silently turn it on.

---

## 7. Strategy Lab (optional research)

- Journal **Backtest** page = R27.5 replay of your journal (SIMULATION banner on results).
- R40 Strategy Lab = offline walk-forward research (`scripts/run_r40_simulation.py` or `POST /api/ui/backtest/r40/run`). Always SIMULATION / manual_only. Not a live recommendation.
- Thresholds in production profiles remain **inherited** until calibration evidence exists (`threshold_registry.yaml`).

---

## 8. Shutdown

```powershell
.\scripts\stop_chakraops.ps1
```

---

## Production readiness gates (operator self-check)

- [ ] Stack on 18800 / 18873 healthy
- [ ] Data health acceptable or Stay in Cash chosen
- [ ] Ticket is manual; no auto-send
- [ ] Journal updated after fills
- [ ] Scheduler off
- [ ] Broker write never used
- [ ] Research backtests labeled SIMULATION and not confused with live recommendations
