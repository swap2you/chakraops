#!/usr/bin/env python3
# ORATS live smoke test. Usage: python scripts/orats_smoke.py SPY
# Exit 0 = PASS, 1 = FAIL. Prints endpoint, HTTP status, row count, sample keys, FINAL VERDICT.
# Token from app.core.config.orats_secrets (hardcoded, private mode).

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

ticker = (sys.argv[1] if len(sys.argv) > 1 else "SPY").strip().upper()

def main() -> int:
    try:
        from app.core.orats.orats_client import probe_orats_live
        result = probe_orats_live(ticker)
    except Exception as e:
        from app.core.orats.orats_client import OratsUnavailableError
        err = e
        if isinstance(e, OratsUnavailableError):
            print("Endpoint used: https://api.orats.io/datav2/live/strikes")
            print("HTTP status:", getattr(e, "http_status", "N/A"))
            print("Row count: 0")
            print("Sample keys: []")
        else:
            print("Endpoint used: https://api.orats.io/datav2/live/strikes")
            print("HTTP status: N/A (request failed)")
            print("Row count: 0")
            print("Sample keys: []")
        print("Error:", err)
        print("FINAL VERDICT: FAIL")
        return 1

    print("Endpoint used: https://api.orats.io/datav2/live/strikes")
    print("HTTP status:", result.get("http_status"))
    print("Row count:", result.get("row_count", 0))
    print("Sample keys:", result.get("sample_keys", []))
    print("FINAL VERDICT: PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
