#!/usr/bin/env python3
"""
ChakraOps - Main orchestrator
"""

import os
import sys
from pathlib import Path

# Try to load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# Try to load config.yaml
config = None
config_path = Path("config.yaml")
example_path = Path("config.yaml.example")

if config_path.exists():
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except ImportError:
        print("Warning: pyyaml not installed. Cannot load config.yaml", file=sys.stderr)
    except Exception as e:
        print(f"Error loading config.yaml: {e}", file=sys.stderr)
        sys.exit(1)
elif example_path.exists():
    print("Info: config.yaml not found. Using config.yaml.example as reference only.", file=sys.stderr)


def get_price_provider():
    """Get configured price provider (Polygon or YFinance fallback)."""
    # Try Polygon first
    if os.getenv("POLYGON_API_KEY"):
        try:
            from app.data.polygon_provider import PolygonProvider
            return PolygonProvider()
        except Exception as e:
            print(f"Warning: Failed to initialize PolygonProvider: {e}", file=sys.stderr)
    
    # Fallback to YFinance
    try:
        from app.data.yfinance_provider import YFinanceProvider
        return YFinanceProvider()
    except ImportError:
        raise ValueError(
            "No price provider available. Install yfinance (pip install yfinance) "
            "or set POLYGON_API_KEY environment variable."
        )


def load_universe_seed() -> list[str]:
    """Load symbol universe from data/universe_seed.txt."""
    repo_root = Path(__file__).parent
    seed_file = repo_root / "app" / "data" / "universe_seed.txt"
    
    if not seed_file.exists():
        raise FileNotFoundError(f"Universe seed file not found: {seed_file}")
    
    symbols = []
    with open(seed_file, "r") as f:
        for line in f:
            symbol = line.strip()
            if symbol and not symbol.startswith("#"):
                symbols.append(symbol.upper())
    
    return symbols


def build_daily_plan_message(regime_result: dict, candidates: list[dict]) -> str:
    """Build daily plan message for Slack."""
    regime = regime_result["regime"]
    confidence = regime_result["confidence"]
    
    lines = [
        "*ChakraOps Daily Plan*",
        "",
        f"*Market Regime:* {regime} (Confidence: {confidence}%)",
        "",
        "*Top CSP Candidates:*",
    ]
    
    # Add top 5 candidates
    for i, candidate in enumerate(candidates[:5], 1):
        symbol = candidate["symbol"]
        score = candidate["score"]
        reasons = candidate.get("reasons", [])
        
        lines.append(f"{i}. *{symbol}* (Score: {score}/100)")
        for reason in reasons[:2]:  # Limit to first 2 reasons
            lines.append(f"   • {reason}")
    
    if not candidates:
        lines.append("No candidates found.")
    
    return "\n".join(lines)


def main():
    """Main orchestrator entry point."""
    try:
        # Step 1: Load env + config (already loaded at module level)
        print("Step 1: Environment and config loaded", file=sys.stderr)
        
        # Step 2: Initialize database
        from app.db.database import init_db
        init_db()
        print("Step 2: Database initialized", file=sys.stderr)
        
        # Step 3: Get price provider
        try:
            provider = get_price_provider()
            provider_name = type(provider).__name__
            print(f"Step 3: Using price provider: {provider_name}", file=sys.stderr)
        except Exception as e:
            error_msg = f"Failed to initialize price provider: {e}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            from app.notify.slack import send_slack
            from app.db.database import log_alert
            try:
                send_slack(error_msg, level="WATCH")
                log_alert(error_msg, level="WATCH")
            except Exception:
                pass  # If Slack fails, continue anyway
            sys.exit(1)
        
        # Step 4: Fetch SPY daily candles and compute regime
        try:
            print("Step 4: Fetching SPY data and computing regime...", file=sys.stderr)
            from app.core.regime import build_weekly_from_daily, compute_regime
            from app.db.database import log_regime_snapshot
            
            df_spy_daily = provider.get_daily("SPY", lookback=400)
            df_spy_weekly = build_weekly_from_daily(df_spy_daily)
            regime_result = compute_regime(df_spy_daily, df_spy_weekly, require_weekly_confirm=True)
            
            # Log regime snapshot
            log_regime_snapshot(
                regime_result["regime"],
                regime_result["confidence"],
                regime_result["details"]
            )
            
            print(f"  Regime: {regime_result['regime']} (Confidence: {regime_result['confidence']}%)", file=sys.stderr)
        except Exception as e:
            error_msg = f"Failed to compute regime: {e}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            from app.notify.slack import send_slack
            from app.db.database import log_alert
            try:
                send_slack(error_msg, level="WATCH")
                log_alert(error_msg, level="WATCH")
            except Exception:
                pass
            sys.exit(1)
        
        # Step 5: Load universe
        try:
            symbols = load_universe_seed()
            print(f"Step 5: Loaded {len(symbols)} symbols from universe", file=sys.stderr)
        except Exception as e:
            error_msg = f"Failed to load universe: {e}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            from app.notify.slack import send_slack
            from app.db.database import log_alert
            try:
                send_slack(error_msg, level="WATCH")
                log_alert(error_msg, level="WATCH")
            except Exception:
                pass
            sys.exit(1)
        
        # Step 6: Fetch candles for each symbol
        print("Step 6: Fetching price data for universe symbols...", file=sys.stderr)
        symbol_to_df = {}
        failed_symbols = []
        
        for symbol in symbols:
            try:
                df = provider.get_daily(symbol, lookback=300)
                symbol_to_df[symbol] = df
                print(f"  ✓ {symbol}: {len(df)} bars", file=sys.stderr)
            except Exception as e:
                print(f"  ✗ {symbol}: {e}", file=sys.stderr)
                failed_symbols.append(symbol)
        
        if failed_symbols:
            warning_msg = f"Failed to fetch data for {len(failed_symbols)} symbols: {', '.join(failed_symbols)}"
            print(f"WARNING: {warning_msg}", file=sys.stderr)
            from app.db.database import log_alert
            log_alert(warning_msg, level="WATCH")
        
        # Step 7: Find CSP candidates
        try:
            print("Step 7: Finding CSP candidates...", file=sys.stderr)
            from app.core.wheel import find_csp_candidates
            from app.db.database import log_csp_candidates
            
            candidates = find_csp_candidates(symbol_to_df, regime_result["regime"])
            log_csp_candidates(candidates)
            
            print(f"  Found {len(candidates)} candidates", file=sys.stderr)
        except Exception as e:
            error_msg = f"Failed to find CSP candidates: {e}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            from app.notify.slack import send_slack
            from app.db.database import log_alert
            try:
                send_slack(error_msg, level="WATCH")
                log_alert(error_msg, level="WATCH")
            except Exception:
                pass
            sys.exit(1)
        
        # Step 8: Build daily plan message
        daily_plan = build_daily_plan_message(regime_result, candidates)
        
        # Step 9: Send Slack message
        try:
            print("Step 9: Sending Slack message...", file=sys.stderr)
            from app.notify.slack import send_slack
            from app.db.database import log_alert
            
            send_slack(daily_plan, level="INFO")
            log_alert(f"Daily plan sent: {regime_result['regime']} regime, {len(candidates)} candidates", level="INFO")
            
            print("  ✓ Slack message sent", file=sys.stderr)
        except Exception as e:
            error_msg = f"Failed to send Slack message: {e}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            from app.db.database import log_alert
            log_alert(error_msg, level="WATCH")
            # Don't exit on Slack failure - data was collected successfully
        
        print("ChakraOps pipeline completed successfully", file=sys.stderr)
        return 0
        
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        error_msg = f"Unexpected error in main pipeline: {e}"
        print(f"FATAL ERROR: {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        
        # Try to send alert
        try:
            from app.notify.slack import send_slack
            from app.db.database import log_alert
            send_slack(error_msg, level="URGENT")
            log_alert(error_msg, level="URGENT")
        except Exception:
            pass  # If alerting fails, at least we logged the error
        
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
