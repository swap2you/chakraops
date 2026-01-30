# ChakraOps

A Python application for managing operations.

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
python scripts/run_and_save.py
```
Output: `out/decision_<timestamp>.json` and `out/decision_latest.json`

**Realtime Mode (Continuous updates during market hours):**
```bash
python scripts/run_and_save.py --realtime
```
- Refreshes every 30-60 seconds (configurable via `config.yaml` → `realtime.refresh_interval`)
- Automatically stops at market close (16:00 by default, configurable via `realtime.end_time`)
- Overwrites `decision_latest.json` on each refresh
- Creates single `decision_YYYY-MM-DD_end.json` at close
- Keeps only end-of-day snapshots (last 7 days by default)

**Test Mode (Diagnostics):**
```bash
python scripts/run_and_save.py --test
```
Shows detailed scoring, chain info, and rejection summaries.

**Launch Live Dashboard:**
```bash
python scripts/live_dashboard.py
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
theta:
  base_url: "http://127.0.0.1:25503/v3"  # Theta Terminal v3 URL
  timeout: 10.0
  fallback_enabled: true  # Use snapshot when Theta unavailable

snapshots:
  retention_days: 7  # Keep snapshots for 7 days
  max_files: 30      # Max files to keep
  output_dir: "out"

realtime:
  refresh_interval: 30  # Seconds between updates (30-60 recommended)
  end_time: "16:00:00"  # Market close (local time)
```

### Theta v3 API Integration

ChakraOps uses ThetaData Terminal v3 REST API for real-time options data.

**Pipeline Pattern:** Based on ThetaData's official examples (basic_pipeline.html):

1. **List Expirations:** `GET /option/list/expirations?symbol={symbol}`
2. **Filter by DTE:** Keep expirations within configured window (default: 7-45 days)
3. **List Strikes:** `GET /option/list/strikes?symbol={symbol}&expiration={exp}`
4. **Fetch Quotes:** `GET /option/snapshot/ohlc?symbol={symbol}&expiration={exp}&strike={strike}&right={C|P}`

**Endpoints used:**
```
GET /option/list/expirations?symbol={symbol}&format=json  # Step 1
GET /option/list/strikes?symbol={symbol}&expiration={exp}&format=json  # Step 3
GET /option/snapshot/ohlc?symbol={symbol}&expiration={exp}&strike={strike}&right=C|P&format=json  # Step 4
GET /stock/snapshot/quote?symbol={symbol}&format=json  # Stock price
```

**Configuration (`config.yaml`):**
```yaml
# DTE window for option chain filtering
dte_min: 7   # Minimum days to expiration
dte_max: 45  # Maximum days to expiration

realtime:
  refresh_interval: 30  # Seconds between pipeline runs (30-60 recommended)
  end_time: "16:00:00"  # Market close time
```

**Concurrency:** Max 4 concurrent requests (Theta Terminal limit)

**Requirements:**
- Theta Terminal v3 running locally on port 25503
- Valid ThetaData subscription (Options.Standard or higher)

**Module:** `app/data/theta_v3_pipeline.py`
- `list_expirations(symbol)` - Get all expirations
- `list_strikes(symbol, expiration)` - Get all strikes for an expiration  
- `snapshot_ohlc(symbol, expiration, strike, right)` - Get OHLC for single contract
- `fetch_chain(symbol, dte_min, dte_max)` - High-level chain fetch (combines all steps)
- `fetch_chain_async(symbol, dte_min, dte_max)` - Async version with concurrent fetching

#### Phase 7.1: Slack Alerts (Optional)

After generating a decision snapshot, the pipeline can send alerts to Slack:

1. **Set environment variable:**
   ```bash
   set SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```
   (Windows) or
   ```bash
   export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
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
