# ChakraOps

A Python application for managing operations.

## Operating ChakraOps

For daily operation, validation, and troubleshooting without reading code:

- **[docs/RUNBOOK.md](docs/RUNBOOK.md)** — Operator runbook: how the system runs, daily workflow, how to interpret Dashboard/Universe/Notifications, alerts (action vs ignore), deployment checklist, common failures.
- **[docs/ALERTING.md](docs/ALERTING.md)** — Alert taxonomy, Slack policy (recommended channels, type→channel mapping, expected frequency, what Slack does *not* do).
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — Deploying to Railway (backend) and Vercel (frontend), env vars, key rotation, cost, failure modes.

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/swap2you/chakraops.git
   cd chakraops
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```

3. Activate the virtual environment:
   - Windows:
     ```bash
     .venv\Scripts\activate
     ```
   - Linux/Mac:
     ```bash
     source .venv/bin/activate
     ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Configure the application (optional):
   - Copy `.env.example` to `.env` and fill in your values
   - Copy `config.yaml.example` to `config.yaml` and customize as needed

## Run

### Phase 7: Decision Intelligence Pipeline (Recommended)

**Generate Decision Snapshot (One-time):**
```bash
python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out
```
Output: `out/decision_<timestamp>.json` and `out/decision_latest.json`

**Realtime Mode (Continuous updates):**
```bash
python scripts/run_and_save.py --realtime --interval 30
```
- Refreshes every `--interval` seconds (default 30)
- Overwrites `decision_latest.json` on each refresh
- Press Ctrl+C to stop

**Launch Live Dashboard:**
```bash
streamlit run app/ui/live_decision_dashboard.py --server.port 8501
```
Open: http://localhost:8501

The dashboard includes:
- Real-time metrics and charts
- Test page for individual symbol chain fetching
- Live/Snapshot data source indicator
- Exclusion breakdown and candidate distribution

**See:** `docs/PHASE7_QUICK_REFERENCE.md` for details

### Configuration

Copy `config.yaml.example` to `config.yaml` and customize:

```yaml
# Options: ORATS Live Data. Set ORATS_API_TOKEN in env (see docs/RUNBOOK_EXECUTION.md).
orats:
  timeout: 30.0

snapshots:
  retention_days: 7  # Keep snapshots for 7 days
  max_files: 30      # Max files to keep
  output_dir: "out"

realtime:
  refresh_interval: 30  # Seconds between updates (30-60 recommended)
  end_time: "16:00:00"  # Market close (local time)

guardrails:
  min_stock_price: 10.0         # Exclude penny stocks (enforced)
  max_trades_per_sector: 3     # Sector diversification (advisory)
  stop_loss_percent: 20.0       # Advisory: exit if underlying drops % below strike; use send_exit_alert when hit
  take_profit_percent: 50.0     # Advisory: close at % of max profit; use send_exit_alert when hit
```

### Guardrails

- **min_stock_price** (default 10): Minimum underlying price; symbols below this are excluded from the universe. Helps avoid penny stocks.
- **max_trades_per_sector** (default 3): Advisory limit on trades per sector; requires sector data for enforcement.
- **stop_loss_percent** / **take_profit_percent**: Advisory exit rules. When a position hits stop or target, call `send_exit_alert(symbol, strike, reason="STOP"|"EXIT", detail=...)` to send a Slack notification.

### ORATS Live Data (Options)

ChakraOps uses **ORATS Live Data** (api.orats.io/datav2) for options expirations, strikes, and equity quotes. No ThetaData terminal or process is required.

**Required:** Set `ORATS_API_TOKEN` in your environment (get token from [ORATS](https://orats.com)). The app also reads the token from `app.core.config.orats_secrets` if not set in env. Never commit the token.

**Health check (backend running):**
- `GET http://localhost:8000/health` → 200, `{"ok": true}`
- `GET http://localhost:8000/api/ops/data-health` → `"status": "OK"` when ORATS is reachable

**Sanity check (no server):**
```bash
python scripts/smoke_orats.py
```

**Strategy validation (CSP criteria):**
```bash
python scripts/test_orats_chain.py AAPL --validate-strategy
```

**Modules:**
- `app/core/options/providers/orats_client.py` – ORATS API client (token from env only)
- `app/core/options/providers/orats_provider.py` – Options chain provider (expirations, strikes, chain)
- `app/data/options_chain_provider.py` – Public interface: `OratsOptionsChainProvider`

**Runbook:** See `docs/RUNBOOK_EXECUTION.md` for env vars, running locally without Theta, and ORATS troubleshooting.

#### Phase 7.1: Slack Alerts (Optional)

After generating a decision snapshot, the pipeline can send alerts to Slack:

1. **Set environment variable:**
   ```bash
   set SLACK_WEBHOOK_URL=<your-webhook-url>
   ```
   (Windows) or
   ```bash
   export SLACK_WEBHOOK_URL=<your-webhook-url>
   ```
   (Linux/Mac)

2. **Run pipeline:** Slack alerts are sent automatically after decision artifact is written
   ```bash
   python scripts/run_and_save.py
   ```

**Note:** Slack alerts are optional. If `SLACK_WEBHOOK_URL` is not set, the pipeline continues normally without alerts.

**See:** `docs/PHASE7_OPERATOR_RUNBOOK.md` for detailed operator guide

### Legacy: Full Orchestrator

```bash
python main.py
```

The application should print "ChakraOps boot OK" and exit successfully.

**Note:** `main.py` is the legacy orchestrator (regime detection, position monitoring, Slack alerts). Phase 7 uses the snapshot-driven pipeline above.

## Development

- Application code is in the `app/` directory
- Tests are in the `tests/` directory
- Scripts are in the `scripts/` directory

### Smoke Tests

Run individual component smoke tests to validate functionality:

```bash
# Test state machine transitions
python scripts/smoke_state_machine.py

# Test regime detection
python scripts/smoke_regime.py

# Test price providers
python scripts/smoke_prices.py

# Test wheel engine
python scripts/smoke_wheel.py

# Test Slack notifications
python scripts/smoke_slack.py
```

### Running Tests

Run the full test suite with pytest:

```bash
pytest tests/
```

### How to interpret pipeline docs

The evaluation pipeline is documented in implementation-truthful form (no aspirational claims):

- **`docs/EVALUATION_PIPELINE.md`** — Stage-by-stage reference: purpose, inputs (with source file or ORATS endpoint), outputs, failure modes mapped to reason codes used in code/UI, and "where to verify" (run JSON path, API response fields).
- **`docs/DATA_DICTIONARY.md`** — Table of every key field shown in the UI: field name, meaning, units/format, source, null/waived behavior, example. Fields not available from ORATS are explicitly marked with fallback/waiver behavior.
- **`docs/ORATS_OPTION_DATA_PIPELINE.md`** — ORATS endpoint reference and data flow.

Use these docs to:

- Interpret run JSON (`out/evaluations/{run_id}.json`) and API responses (`/api/view/evaluation/latest`, `/api/view/symbol-diagnostics`).
- Map UI labels and reason codes (e.g. `POSITION_BLOCKED`, `DATA_INCOMPLETE_FATAL`, `REGIME_RISK_OFF`) to the pipeline stage and code path.
- Understand which fields come from which ORATS endpoint and how missing or waived fields are handled.

The React app exposes a **Pipeline** page (route `/pipeline`) with the same seven stages (Universe → … → Score & Band); expanding a stage shows purpose, inputs with source, outputs, failure modes with reason codes, and where to verify.
