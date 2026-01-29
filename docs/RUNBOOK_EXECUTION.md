# ChakraOps Local Execution Runbook

This runbook provides step-by-step instructions for running ChakraOps locally on your machine.

## Prerequisites

- Java required (to run ThetaTerminalv3.jar)
- Python 3 with Streamlit (to run ChakraOps UI)
- ThetaTerminal v3 must be running locally on port 25503

## Directory (Confirmed)

The ThetaTerminal files are located at:
```
C:\Development\Workspace\ChakraOps\chakraops\app\thedata
```

Confirmed files present:
- ThetaTerminalv3.jar
- config.toml
- creds.txt

## Step 1: Start Theta Terminal (MANDATORY)

**PowerShell commands (exact):**
```powershell
cd C:\Development\Workspace\ChakraOps\chakraops\app\thedata
java -jar ThetaTerminalv3.jar
```

**Expected output (must see):**
```
Starting server at: http://0.0.0.0:25503
CONNECTED: Bundle: OPTION.STANDARD
```

**⚠️ WARNING: If Theta Terminal is not running, ChakraOps will not work.**

## Execution Options

### Option A (Recommended): Python Virtual Environment (.venv)

Assume Windows / PowerShell. Use a `.venv` in the app directory (create once with `python -m venv .venv` if needed).

**Activate venv:**
```powershell
cd C:\Development\Workspace\ChakraOps\chakraops
.\.venv\Scripts\Activate.ps1
```

**Install dependencies:**
```powershell
pip install -r requirements.txt
```

**Run tests:**
```powershell
cd C:\Development\Workspace\ChakraOps
python -m pytest chakraops/tests/ -v
```

**Start Streamlit live dashboard:**
```powershell
cd C:\Development\Workspace\ChakraOps\chakraops
python -m scripts.live_dashboard
```

**Deactivate venv:**
```powershell
deactivate
```

### Option B (Fallback): System Python (no venv)

**⚠️ WARNING: This is NOT the recommended path. Use Option A when possible.**

**Install dependencies:**
```powershell
cd C:\Development\Workspace\ChakraOps\chakraops
pip install -r requirements.txt
```

**Run tests:**
```powershell
cd C:\Development\Workspace\ChakraOps
python -m pytest chakraops/tests/ -v
```

**Start Streamlit live dashboard:**
```powershell
cd C:\Development\Workspace\ChakraOps\chakraops
python -m scripts.live_dashboard
```

## Fail Fast

To quickly verify ThetaTerminal is running and accessible, run this PowerShell command:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:25503/v3/stock/list/symbols?format=json" -UseBasicParsing | Select-Object StatusCode
```

**Expected output:**
```
StatusCode
----------
       200
```

If you see `200`, ThetaTerminal is running correctly. If you see connection errors or timeouts, return to Step 1.

## Database Location

ChakraOps uses a local SQLite database for persistence (Phase 1A MVP):

**Database file location:**
```
C:\Development\Workspace\ChakraOps\chakraops\data\chakraops.db
```

The database is automatically created on first run. It contains:
- **trades**: Immutable trade ledger (SELL_TO_OPEN, BUY_TO_CLOSE, ASSIGN, etc.)
- **positions**: Current position state (derived from trades)
- **alerts**: Alert lifecycle (OPEN/ACKED/ARCHIVED)
- **portfolio_snapshots**: Manual account value and cash snapshots (with brokerage selector)
- **csp_candidates**: CSP candidate recommendations (with executed flag)
- **symbol_universe**: Editable symbol universe (enabled/disabled flags)
- **regime_snapshots**: Market regime detection results

**Note:** The database file is created automatically when you run `python main.py` or access the Streamlit dashboard. No manual setup required.

### Clean Baseline Reset (DEV ONLY)

The dashboard includes a "Reset Local Trading State (DEV ONLY)" button in the sidebar under DEV Controls. This will:
- Delete the local SQLite database file (`chakraops.db`)
- Reinitialize the database schema cleanly
- Log a reset event
- **WARNING:** This deletes ALL local trading data (trades, positions, alerts, snapshots, candidates)

This is useful for:
- Development/testing cleanups
- Resetting to a clean baseline
- Troubleshooting data corruption issues

**This does NOT affect:**
- Code files
- Schema definitions
- Test files
- Configuration files

### Symbol Universe Management

The dashboard includes a "Symbol Universe Manager" section that allows you to:
- View all symbols in the universe with their enabled/disabled status
- Add new symbols to the universe
- Enable/disable symbols (only enabled symbols are used for CSP candidate generation)
- Add notes for each symbol

**Default Universe:** On first run, the system populates with FAANG + SPY/QQQ:
- AAPL, MSFT, GOOGL, AMZN, META, SPY, QQQ

**CSP Candidate Filtering:** Only symbols with `enabled = true` in the universe table are used for CSP candidate generation. This filter is applied BEFORE any scoring or analysis.

## Troubleshooting

- **If port 25503 is not reachable:** Confirm ThetaTerminal Step 1 is running and not blocked by firewall.
- **If CONNECTED line does not appear:** creds/config issue; stop and fix before running ChakraOps.
- **If ChakraOps fails to connect:** Verify ThetaTerminal is still running and shows the expected output from Step 1.
- **If smoke test fails:** Ensure ThetaTerminal is running and accessible before running ChakraOps.
- **If database errors occur:** Ensure the `data/` directory exists and is writable. The database is created automatically on first run.
