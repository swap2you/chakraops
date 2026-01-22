# ChakraOps Local Execution Runbook

This runbook provides step-by-step instructions for running ChakraOps locally on your machine.

## Prerequisites

- Java required (to run ThetaTerminalv3.jar)
- Streamlit required (to run ChakraOps UI)
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

## Step 2: Run ChakraOps

**From project root, PowerShell commands:**
```powershell
cd C:\Development\Workspace\ChakraOps\chakraops
streamlit run app/web/main.py
```

(If your entrypoint differs, replace only the last command with the correct entrypoint.)

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

## Troubleshooting

- **If port 25503 is not reachable:** Confirm ThetaTerminal Step 1 is running and not blocked by firewall.
- **If CONNECTED line does not appear:** creds/config issue; stop and fix before running ChakraOps.
- **If ChakraOps fails to connect:** Verify ThetaTerminal is still running and shows the expected output from Step 1.
- **If smoke test fails:** Ensure ThetaTerminal is running and accessible before running ChakraOps.
