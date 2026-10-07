#!/usr/bin/env python3
"""
ChakraOps - Main orchestrator (Legacy)

⚠️ NOTE: This is the legacy orchestrator for position management, regime detection,
and Slack alerts. For Phase 7 decision intelligence pipeline, use:
- scripts/run_and_save.py (generate snapshots)
- scripts/live_dashboard.py (view dashboard)

This file remains for legacy workflows but is NOT part of the Phase 7 golden path.
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
    """Get configured market data provider (ThetaData primary)."""
    try:
        from app.core.market_data.factory import get_market_data_provider
        return get_market_data_provider()
    except Exception as e:
        print(f"Error: Failed to initialize market data provider: {e}", file=sys.stderr)
        raise


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


def build_daily_plan_message(
    regime_result: dict,
    candidates: list[dict],
    positions: list = None,
    position_decisions: list = None,
) -> str:
    """Build daily plan message for Slack.
    
    Parameters
    ----------
    regime_result:
        Market regime result dictionary.
    candidates:
        List of CSP candidate dictionaries.
    positions:
        Optional list of Position objects (for reference).
    position_decisions:
        Optional list of ActionDecision objects (pre-computed decisions).
    """
    regime = regime_result["regime"]
    confidence = regime_result["confidence"]
    
    lines = [
        "*ChakraOps Daily Plan*",
        "",
        f"*Market Regime:* {regime} (Confidence: {confidence}%)",
        "",
    ]
    
    # Action Alerts section (HIGH urgency decisions)
    high_urgency_decisions = []
    if position_decisions:
        high_urgency_decisions = [
            (pos, dec) for pos, dec in zip(positions or [], position_decisions)
            if dec and dec.urgency.value == "HIGH"
        ]
    
    if high_urgency_decisions:
        lines.append("🔥 *Action Alerts*")
        lines.append("")
        for position, decision in high_urgency_decisions:
            symbol = position.symbol
            state = position.state or position.status
            action = decision.action.value
            urgency = decision.urgency.value
            key_reason = decision.reasons[0] if decision.reasons else "No reason provided"
            
            line = f"*{symbol}* | {state} | {action} | {urgency} | {key_reason}"
            lines.append(line)
            
            # Add roll plan details if action is ROLL
            if decision.action.value == "ROLL" and decision.roll_plan:
                roll_plan = decision.roll_plan
                lines.append(f"   → Roll: {roll_plan.suggested_strike:.0f} @ {roll_plan.suggested_expiry} ({roll_plan.roll_type})")
        
        lines.append("")
    
    # Open Positions Decisions section
    lines.append("📌 *Open Positions Decisions*")
    lines.append("")
    
    if position_decisions and positions:
        has_any_decisions = False
        for position, decision in zip(positions, position_decisions):
            if not decision:
                continue
            
            has_any_decisions = True
            symbol = position.symbol
            state = position.state or position.status
            action = decision.action.value
            urgency = decision.urgency.value
            key_reason = decision.reasons[0] if decision.reasons else "No reason provided"
            
            line = f"{symbol} | {state} | {action} | {urgency} | {key_reason}"
            lines.append(line)
            
            # Add roll plan details if action is ROLL
            if decision.action.value == "ROLL" and decision.roll_plan:
                roll_plan = decision.roll_plan
                lines.append(f"   → Roll: {roll_plan.suggested_strike:.0f} @ {roll_plan.suggested_expiry} ({roll_plan.roll_type})")
        
        if not has_any_decisions:
            lines.append("No open positions.")
    else:
        lines.append("No open positions.")
    
    lines.append("")
    
    # Top CSP Candidates section
    lines.append("*Top CSP Candidates:*")
    
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
        
        # Step 5: Load universe (filter by enabled symbols)
        try:
            # Try to get enabled symbols from database first
            from app.core.persistence import get_enabled_symbols
            try:
                enabled_symbols = get_enabled_symbols()
                if enabled_symbols:
                    symbols = enabled_symbols
                    print(f"Step 5: Loaded {len(symbols)} enabled symbols from universe database", file=sys.stderr)
                else:
                    # Fallback to universe_seed.txt if database is empty
                    symbols = load_universe_seed()
                    print(f"Step 5: Loaded {len(symbols)} symbols from universe_seed.txt (fallback)", file=sys.stderr)
            except Exception:
                # Fallback to universe_seed.txt if database not available
                symbols = load_universe_seed()
                print(f"Step 5: Loaded {len(symbols)} symbols from universe_seed.txt (fallback)", file=sys.stderr)
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
        
        # Step 7: Find CSP candidates and score assignment-worthiness (Phase 1B)
        try:
            print("Step 7: Finding CSP candidates...", file=sys.stderr)
            from app.core.wheel import find_csp_candidates
            from app.core.assignment_scoring import score_assignment_worthiness
            from app.core.persistence import save_assignment_profile, is_assignment_blocked, create_alert
            
            candidates = find_csp_candidates(symbol_to_df, regime_result["regime"])
            
            # Score assignment-worthiness for each candidate (Phase 1B)
            actionable_candidates = []
            blocked_count = 0
            
            for candidate in candidates:
                try:
                    # Score assignment-worthiness
                    assignment_result = score_assignment_worthiness(
                        candidate,
                        regime_result["regime"]
                    )
                    
                    # Add assignment data to candidate
                    candidate["assignment_score"] = assignment_result["assignment_score"]
                    candidate["assignment_label"] = assignment_result["assignment_label"]
                    candidate["assignment_reasons"] = assignment_result["assignment_reasons"]
                    
                    # Save assignment profile
                    save_assignment_profile(
                        symbol=candidate["symbol"],
                        assignment_score=assignment_result["assignment_score"],
                        assignment_label=assignment_result["assignment_label"],
                        operator_override=False,  # Will be set by operator in UI
                        override_reason=None,
                    )
                    
                    # Check if blocked (RENT_ONLY without override)
                    if is_assignment_blocked(candidate["symbol"]):
                        blocked_count += 1
                        # Don't add to actionable candidates, but still log for UI display
                        candidate["blocked"] = True
                        candidate["blocked_reason"] = "Not Assignment-Worthy (RENT_ONLY)"
                    else:
                        candidate["blocked"] = False
                        actionable_candidates.append(candidate)
                
                except RuntimeError as e:
                    # Assignment scoring failed - block CSP and emit HALT alert
                    error_msg = f"Assignment scoring failed for {candidate.get('symbol', 'UNKNOWN')}: {e}"
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    create_alert(
                        f"Assignment scoring failed for {candidate.get('symbol', 'UNKNOWN')}. CSP blocked.",
                        level="HALT"
                    )
                    candidate["blocked"] = True
                    candidate["blocked_reason"] = "Assignment scoring error"
                    blocked_count += 1
            
            print(f"  Found {len(candidates)} candidates ({len(actionable_candidates)} actionable, {blocked_count} blocked)", file=sys.stderr)
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
        
        # Step 9: Monitor open positions and evaluate with Action Engine
        position_decisions = []
        open_positions = []
        try:
            print("Step 9: Monitoring open positions...", file=sys.stderr)
            from app.core.engine.position_engine import PositionEngine
            from app.core.engine.risk_engine import RiskEngine
            from app.core.engine.actions import decide_position_action
            from app.core.engine.alert_dedupe import AlertDedupeEngine
            from app.notify.slack import send_slack
            from app.db.database import log_alert
            
            position_engine = PositionEngine()
            risk_engine = RiskEngine()
            dedupe_engine = AlertDedupeEngine()
            open_positions = position_engine.get_open_positions()
            
            if open_positions:
                print(f"  Evaluating {len(open_positions)} open positions with Action Engine...", file=sys.stderr)
                
                for position in open_positions:
                    # Build market context for Action Engine
                    market_context = {"regime": regime_result["regime"]}
                    
                    # Fetch current price and EMA200
                    try:
                        df = provider.get_daily(position.symbol, lookback=250)
                        if not df.empty:
                            df = df.sort_values("date", ascending=True).reset_index(drop=True)
                            df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
                            df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
                            latest = df.iloc[-1]
                            current_price = float(latest["close"])
                            market_context["underlying_price"] = current_price
                            market_context["current_price"] = current_price
                            market_context["ema200"] = float(latest["ema200"])
                            market_context["ema50"] = float(latest["ema50"])
                            market_context["price_df"] = df
                            
                            # Calculate ATR proxy (3% default)
                            atr_pct = 0.03
                            market_context["atr_pct"] = atr_pct
                            
                            # Calculate premium collected percentage
                            if position.strike and position.strike > 0 and position.contracts > 0:
                                premium_per_contract = position.premium_collected / position.contracts
                                premium_pct = (premium_per_contract / (position.strike * 100)) * 100
                                market_context["premium_collected_pct"] = premium_pct
                    except Exception as e:
                        print(f"  ⚠ Could not fetch price data for {position.symbol}: {e}", file=sys.stderr)
                    
                    # Evaluate position with Action Engine
                    action_decision = None
                    try:
                        action_decision = decide_position_action(position, market_context)
                        position_decisions.append(action_decision)
                        print(f"  ✓ {position.symbol}: {action_decision.action.value} ({action_decision.urgency.value})", file=sys.stderr)
                    except Exception as e:
                        print(f"  ✗ Failed to evaluate {position.symbol} with Action Engine: {e}", file=sys.stderr)
                        position_decisions.append(None)
                    
                    # Also evaluate with Risk Engine for backward compatibility (ACTION_REQUIRED alerts)
                    try:
                        evaluation = risk_engine.evaluate_position(position, market_context)
                        
                        # Use Action Engine decision for deduplication
                        # Only send alerts if dedupe engine allows it (or if no action_decision available)
                        should_send_alert = True  # Default: allow if no Action Engine decision
                        if action_decision:
                            should_send_alert = dedupe_engine.should_notify(
                                position.symbol,
                                action_decision,
                                cooldown_minutes=60
                            )
                        
                        if evaluation["status"] == "ACTION_REQUIRED" and should_send_alert:
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
                                # Record notification in dedupe engine
                                if action_decision:
                                    dedupe_engine.record_notification(position.symbol, action_decision)
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
                                # Record notification in dedupe engine
                                if action_decision:
                                    dedupe_engine.record_notification(position.symbol, action_decision)
                                print(f"  ✓ ACTION_REQUIRED alert sent for {position.symbol}", file=sys.stderr)
                        elif evaluation["status"] == "ACTION_REQUIRED" and not should_send_alert:
                            # Alert suppressed by dedupe engine
                            print(f"  ⊘ Alert suppressed for {position.symbol} (duplicate or cooldown)", file=sys.stderr)
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
        daily_plan = build_daily_plan_message(
            regime_result,
            candidates,
            positions=open_positions,
            position_decisions=position_decisions,
        )
        
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
