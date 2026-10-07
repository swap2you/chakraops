# ChakraOps NEEWA operating contract

Canonical checkout: `C:\Users\swap2\NEEWA-Personal\projects\ChakraOps`.

Origin: `https://github.com/swap2you/chakraops.git`, branch `main`.

Registry id: `PRJ-CHAKRAOPS`. One entry. There is no second dev tree.

## Ownership

- NEEWA coordinates missions and receipts.
- Cursor implements, one writer at a time, on this checkout.
- ChatGPT-authenticated Codex (`codex exec`, not an OpenAI API key) validates read-only after the writer yields.
- The Windows worker identity is the interactive user that runs `%LOCALAPPDATA%\NEEWA\worker`. A Linux coordinator dispatches work to that worker. A path written in a document is not remote filesystem access.
- Recurring snapshot, regression, and market-health schedules stay off.
- Trading stays manual. No broker writes, no public deployment, no unrequested Slack sends.
- ORATS is the options data provider. Credentials stay in `backend/.env`.

## Model routing

Implementation uses one Cursor agent model from the live inventory. This session's inventory includes `grok-4.7-high`. Validation uses Codex CLI signed in with ChatGPT. On 2026-10-07 the signed-in account rejected `gpt-6.1-sol`. The live Codex catalog lists `gpt-6-astra` with effort `high`, and a read-only probe returned `pong`. This route must not fall back to `OPENAI_API_KEY`.

## Continuation

`MISSION-20261007T154400Z-0991E812` reached `OWNER_REVIEW` after a child failure. That state is not success. A child timeout or `OWNER_REVIEW` without an independent pass is incomplete. Same-mission continuation is only the supported `neewa_mission.py step` path, and that path skips terminal states. A terminal mission is closed with a same-state note, then exactly one linked successor is submitted. Do not relabel a failed stage as success.

## What the application is

ChakraOps is a local decision-support app for a wheel-style workflow: cash-secured puts, covered calls, and shares. It ranks candidates, shows risk and data freshness, and builds a manual ticket. It does not place orders. A passing payoff calculation is not evidence of profitability. Research that claims an edge has to account for fees, slippage, liquidity, assignment, drawdown, and out-of-sample results.

Configured strategy material lives in `backend/config/`. Account inputs stay in local data stores and are not committed.

ORATS supplies option chains. Snapshots and replay fixtures exist for tests. The exchange calendar and quote timestamps are part of the data-health gates; stale data must stay visible as stale. Migrations live under the backend Alembic/SQLAlchemy data platform. Do not change risk thresholds to make a screen look healthy.

## UI routes

The React app in `frontend/src/app/App.tsx` serves:

| Route | Outcome |
| --- | --- |
| `/` | Dashboard home |
| `/opportunities` | Strategy candidates (CSP, shares, ETF via query) |
| `/universe`, `/universe-admin`, `/universe-health` | Symbol universe and its health |
| `/symbol-diagnostics`, `/system` | One-symbol and system diagnostics |
| `/notifications`, `/journal`, `/learn` | Alerts, notes, education |
| `/ticket` | Manual trade ticket |
| `/today`, `/weekly`, `/reports` | Daily and review packs |
| `/backtest`, `/paper` | Replay and paper views |
| `/portfolio` | Holdings. `/positions` redirects here |
| `/strategy-builder` | Strategy configuration view |
| `/wheel` | Wheel view when that flag is on; otherwise home |
| `/login` | Sign-in when auth is required |

Loading, empty, and error states are per page. Backend contracts are under `backend/app/api/`. Local review URLs are http://127.0.0.1:18873 and http://127.0.0.1:18800.

## Commands

```text
powershell -NoProfile -File .\chakra.ps1 setup
powershell -NoProfile -File .\chakra.ps1 start
powershell -NoProfile -File .\chakra.ps1 stop
powershell -NoProfile -File .\chakra.ps1 test
powershell -NoProfile -File .\chakra.ps1 status
```

## Next work

Keep one mission on this checkout. The next bounded stage is source-grounded validation of data freshness and the highest failing user journey, then a fix that fits the worker timeout. Do not register schedules or enable broker execution.
