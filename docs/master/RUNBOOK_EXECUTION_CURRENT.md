# ChakraOps R70+ Execution Runbook (CURRENT)

**Repo:** `C:\Development\Workspace\ChakraOps-dev\chakraops` · branch `main` · `SINGLE_OPERATOR_MAINLINE_LOOP_MODE`  
**Domain (deferred deploy):** `https://chakraops.cloud` — do not touch `dauji.info` during local remediation.

Historical R24–R35 Caddy/world docs remain under archived release notes; this file is operator SoT for R70+.

## Safety (permanent)

- `manual_only=true`
- `trade_execution=false`
- Robinhood **read-only** (allowlist fail-closed)
- Legacy scheduler **off** locally
- Stay in Cash remains valid
- Never invoke broker write tools (place/buy/sell/submit/cancel/replace/exercise/assign/transfer/rebalance/deposit/withdraw)

## Local ports & process ownership

| Role | Port | Start |
|------|------|-------|
| Backend (uvicorn) | `18800` | `scripts/start_chakraops.ps1` |
| Frontend (Vite) | `18873` | same script (waits for LISTEN — R70-DEF-072) |

Prefer `127.0.0.1`. Stop with `scripts/stop_chakraops.ps1`.

## Auth

| Mode | Behavior |
|------|----------|
| Local default | `CHAKRAOPS_AUTH_MODE=disabled` — open for operator/dev |
| Production-like | `CHAKRAOPS_AUTH_MODE=required` + bootstrap under `C:\ChakraOpsSecrete` |
| Production | `CHAKRAOPS_PRODUCTION=true` forces required; fail-closed if secrets missing |

Bootstrap (hashes only, never commit secrets):

```powershell
.\scripts\bootstrap_local_auth.ps1
```

Fixed admins only: `swap2you`, `swapnilpatil`, `daudada`, `admin`. No signup/forgot-password.

## Robinhood (app OAuth ≠ Cursor MCP)

Cursor’s Robinhood MCP session is **not** ChakraOps auth.

```powershell
.\scripts\robinhood_mcp_authorize.ps1
```

Complete browser consent, then Portfolio → **Sync**. Tokens under `C:\ChakraOpsSecrete\robinhood\`. Never paste bearer tokens into chat.

## Evaluation

- **Primary LIVE authority:** exclusive coordinator `run_universe_evaluation_exclusive` (`PRIMARY_LIVE_EVAL_AUTHORITY`)
  - UI: `POST /api/ui/eval/run`
  - Ops: `POST /api/ops/evaluate` and `POST /api/ops/evaluate-now` (alias → same coordinator)
- **Canonical recommendations:** `decision_engine.live_service` over `EvaluationStoreV2` / `decision_latest.json`
- Ledger: successful exclusive runs call `save_run` + `update_latest_pointer` (`last_completed_run_id`)
- **Secondary (non-authoritative):** `scripts/run_and_save.py` (`SECONDARY_EVAL_PATH`), single-symbol merge (`SECONDARY_SYMBOL_MERGE_PATH`) — offline/diagnostics only; do not use for LIVE authority
- No auto full-universe eval on local start when schedulers are off

## Gates / calendars (R70-DEF-041/042)

- Macro calendar: static US FOMC/NFP/CPI markers; unconfigured stub → `MACRO_CALENDAR_UNAVAILABLE` (fail closed)
- Session gate: short sessions / min trading days wired into decision engine
- Market hours: NYSE holiday calendar via `market_calendar.is_market_open_today` (weekdays are not always OPEN)

## Persistence honesty

Production requires Postgres for the SQLAlchemy platform gate. Critical portfolio/broker snapshot/position paths may still use durable local stores; docs must not claim “all stores are Postgres” until migrated (see R70-DEF-030/031).

## Quality gates

```powershell
cd chakraops
.\.venv\Scripts\python.exe -m pytest -q --tb=line
.\.venv\Scripts\python.exe ..\scripts\quality_gate_r70.py
cd ..\frontend
npm.cmd run typecheck
npm.cmd run build
```

## Production topology (deploy still deferred)

`deploy/docker-compose.prod.yml` · Cloudflare Access → Tunnel → frontend:80 → `/api` → api · Postgres mandatory · no public 18800/18873.

Secrets: Linux `/opt/chakraops/secrets` · Windows `C:\ChakraOpsSecrete`.
