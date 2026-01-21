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
        
        # Step 8: Generate trade plans and send alerts
        try:
            print("Step 8: Generating trade plans...", file=sys.stderr)
            from app.core.engine.csp_trade_engine import CSPTradeEngine
            from app.notify.slack import send_slack
            from app.db.database import log_alert
            from datetime import datetime, date
            
            trade_engine = CSPTradeEngine()
            portfolio_value = float(os.getenv("PORTFOLIO_VALUE", "100000"))  # Default $100k
            
            trade_plans = []
            for candidate in candidates:
                # Only process candidates with contract details
                if candidate.get("contract"):
                    trade_plan = trade_engine.generate_trade_plan(
                        candidate,
                        portfolio_value,
                        regime_result["regime"]
                    )
                    if trade_plan:
                        trade_plans.append(trade_plan)
            
            # Send Slack alerts for each trade plan
            for plan in trade_plans:
                try:
                    # Calculate DTE
                    expiry_date = datetime.fromisoformat(plan["expiry"]).date()
                    dte = (expiry_date - date.today()).days
                    
                    # Format message
                    message_lines = [
                        "[ACTION REQUIRED] SELL CSP",
                        f"Symbol: {plan['symbol']}",
                        f"Strike: {plan['strike']:.0f}",
                        f"Expiry: {plan['expiry']} ({dte} DTE)",
                        f"Contracts: {plan['contracts']}",
                        f"Capital Required: ${plan['capital_required']:,.0f}",
                        "Rationale:",
                    ]
                    
                    # Add rationale items - extract key points
                    rationale_added = set()
                    for reason in plan.get("rationale", []):
                        reason_lower = reason.lower()
                        # Extract delta
                        if "delta:" in reason_lower and "delta" not in rationale_added:
                            try:
                                delta_part = reason.split("Delta:")[1].strip().split()[0]
                                delta_val = float(delta_part)
                                message_lines.append(f"- Delta ~{delta_val:.2f}")
                                rationale_added.add("delta")
                            except (ValueError, IndexError):
                                pass
                        # Extract uptrend
                        elif ("uptrend" in reason_lower or "ema200" in reason_lower) and "uptrend" not in rationale_added:
                            message_lines.append("- Uptrend above EMA200")
                            rationale_added.add("uptrend")
                        # Extract pullback
                        elif ("pullback" in reason_lower or "ema50" in reason_lower) and "pullback" not in rationale_added:
                            message_lines.append("- Pullback near EMA50")
                            rationale_added.add("pullback")
                        # Extract RSI if oversold
                        elif "rsi" in reason_lower and "oversold" in reason_lower and "rsi" not in rationale_added:
                            rsi_part = reason.split("RSI:")[1].strip().split()[0] if "RSI:" in reason else ""
                            if rsi_part:
                                message_lines.append(f"- RSI {rsi_part} (oversold)")
                            else:
                                message_lines.append("- RSI oversold")
                            rationale_added.add("rsi")
                    
                    message = "\n".join(message_lines)
                    
                    send_slack(message, level="URGENT")
                    log_alert(f"Trade plan alert sent for {plan['symbol']}", level="INFO")
                    print(f"  ✓ Trade plan alert sent for {plan['symbol']}", file=sys.stderr)
                except Exception as e:
                    print(f"  ✗ Failed to send trade plan alert for {plan['symbol']}: {e}", file=sys.stderr)
                    log_alert(f"Failed to send trade plan alert: {e}", level="WATCH")
            
            if trade_plans:
                print(f"  Sent {len(trade_plans)} trade plan alerts", file=sys.stderr)
        except Exception as e:
            error_msg = f"Failed to generate trade plans: {e}"
            print(f"WARNING: {error_msg}", file=sys.stderr)
            from app.db.database import log_alert
            log_alert(error_msg, level="WATCH")
            # Don't exit - continue with daily plan
        
        # Step 9: Monitor open positions and send alerts
        try:
            print("Step 9: Monitoring open positions...", file=sys.stderr)
            from app.core.engine.position_engine import PositionEngine
            from app.core.engine.risk_engine import RiskEngine
            from app.notify.slack import send_slack
            from app.db.database import log_alert
            
            position_engine = PositionEngine()
            risk_engine = RiskEngine()
            open_positions = position_engine.get_open_positions()
            
            if open_positions:
                print(f"  Evaluating {len(open_positions)} open positions...", file=sys.stderr)
                
                for position in open_positions:
                    # Build market context
                    market_context = {"regime": regime_result["regime"]}
                    
                    # Fetch current price and EMA200
                    try:
                        df = provider.get_daily(position.symbol, lookback=250)
                        if not df.empty:
                            df = df.sort_values("date", ascending=True).reset_index(drop=True)
                            df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
                            latest = df.iloc[-1]
                            market_context["current_price"] = float(latest["close"])
                            market_context["ema200"] = float(latest["ema200"])
                    except Exception as e:
                        print(f"  ⚠ Could not fetch price data for {position.symbol}: {e}", file=sys.stderr)
                    
                    # Evaluate position
                    try:
                        evaluation = risk_engine.evaluate_position(position, market_context)
                        
                        if evaluation["status"] == "ACTION_REQUIRED":
                            # Check for roll suggestion if CSP position
                            roll_suggestion = None
                            if position.position_type == "CSP":
                                try:
                                    from app.core.engine.roll_engine import RollEngine
                                    from app.data.orats_client import OratsClient
                                    
                                    # Initialize ORATS client
                                    orats_client = None
                                    try:
                                        orats_client = OratsClient()
                                    except Exception:
                                        pass  # ORATS not available
                                    
                                    if orats_client:
                                        # Enhance market context with EMA50 and price_df
                                        enhanced_context = market_context.copy()
                                        try:
                                            df = provider.get_daily(position.symbol, lookback=250)
                                            if not df.empty:
                                                df = df.sort_values("date", ascending=True).reset_index(drop=True)
                                                df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
                                                latest = df.iloc[-1]
                                                enhanced_context["ema50"] = float(latest["ema50"])
                                                enhanced_context["price_df"] = df
                                        except Exception:
                                            pass
                                        
                                        # Get roll suggestion
                                        roll_engine = RollEngine(orats_client=orats_client)
                                        roll_suggestion = roll_engine.suggest_roll(position, enhanced_context)
                                except Exception as e:
                                    print(f"  ⚠ Could not generate roll suggestion for {position.symbol}: {e}", file=sys.stderr)
                            
                            # If roll suggestion exists, send roll alert
                            if roll_suggestion:
                                # Format current position description
                                current_desc = f"{position.position_type}"
                                if position.strike:
                                    current_desc += f" {position.strike:.0f}"
                                if position.expiry:
                                    current_desc += f" exp {position.expiry}"
                                
                                # Format suggested position description
                                suggested_desc = f"{position.position_type}"
                                suggested_desc += f" {roll_suggestion['suggested_strike']:.0f}"
                                suggested_desc += f" exp {roll_suggestion['suggested_expiry']}"
                                
                                # Format net credit with + sign
                                net_credit = roll_suggestion['estimated_net_credit']
                                net_credit_str = f"+${net_credit:.2f}" if net_credit >= 0 else f"${net_credit:.2f}"
                                
                                # Format message
                                message_lines = [
                                    "[ROLL SUGGESTION]",
                                    f"Symbol: {position.symbol}",
                                    f"Current: {current_desc}",
                                    f"Suggested: {suggested_desc}",
                                    f"Net Credit: {net_credit_str}",
                                    "Reasons:",
                                ]
                                
                                # Add reasons from roll suggestion
                                for reason in roll_suggestion.get("reasons", []):
                                    message_lines.append(f"- {reason}")
                                
                                # Add regime if available
                                if market_context.get("regime"):
                                    regime = market_context["regime"]
                                    if regime == "RISK_ON":
                                        message_lines.append("- Regime RISK_ON")
                                    elif regime == "RISK_OFF":
                                        message_lines.append("- Regime RISK_OFF")
                                
                                message = "\n".join(message_lines)
                                
                                # Send to urgent alerts channel
                                send_slack(message, level="URGENT")
                                log_alert(f"Roll suggestion sent for {position.symbol}", level="URGENT")
                                print(f"  ✓ Roll suggestion alert sent for {position.symbol}", file=sys.stderr)
                            else:
                                # No roll suggestion - send standard ACTION_REQUIRED alert
                                # Format position description
                                position_desc = f"{position.position_type}"
                                if position.strike:
                                    position_desc += f" {position.strike:.0f}"
                                if position.expiry:
                                    position_desc += f" exp {position.expiry}"
                                
                                # Format message
                                message_lines = [
                                    "[ACTION REQUIRED]",
                                    f"Symbol: {position.symbol}",
                                    f"Position: {position_desc}",
                                    f"Status: {evaluation['status']}",
                                    "Reasons:",
                                ]
                                
                                # Add reasons
                                for reason in evaluation.get("reasons", []):
                                    message_lines.append(f"- {reason}")
                                
                                # Add suggested next step
                                message_lines.append("")
                                message_lines.append("Suggested next step:")
                                message_lines.append("- Roll forward or accept assignment")
                                
                                message = "\n".join(message_lines)
                                
                                # Send to urgent alerts channel
                                send_slack(message, level="URGENT")
                                log_alert(f"Position alert sent for {position.symbol}: ACTION_REQUIRED", level="URGENT")
                                print(f"  ✓ ACTION_REQUIRED alert sent for {position.symbol}", file=sys.stderr)
                    except Exception as e:
                        print(f"  ✗ Failed to evaluate position {position.symbol}: {e}", file=sys.stderr)
                        log_alert(f"Failed to evaluate position {position.symbol}: {e}", level="WATCH")
            else:
                print("  No open positions to monitor", file=sys.stderr)
        except Exception as e:
            error_msg = f"Failed to monitor positions: {e}"
            print(f"WARNING: {error_msg}", file=sys.stderr)
            from app.db.database import log_alert
            log_alert(error_msg, level="WATCH")
            # Don't exit - continue with daily plan
        
        # Step 10: Build daily plan message
        daily_plan = build_daily_plan_message(regime_result, candidates)
        
        # Step 11: Send Slack message
        try:
            print("Step 11: Sending Slack message...", file=sys.stderr)
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
