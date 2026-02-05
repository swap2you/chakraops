#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Decision Dashboard (Phase 6A) - Read-only visualization of decision runs.

⚠️ DEPRECATED: This module is deprecated in favor of app/ui/live_decision_dashboard.py (Phase 7).
This file is kept for backward compatibility but should not be used for new development.
Use scripts/live_dashboard.py instead.
"""

import json
from pathlib import Path
from typing import Dict, Any

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def load_decision_data(json_path: Path) -> Dict[str, Any]:
    """Load decision data from JSON file."""
    if not json_path.exists():
        raise FileNotFoundError(f"Decision file not found: {json_path}")
    
    with open(json_path, "r") as f:
        return json.load(f)


def render_dashboard_html(data: Dict[str, Any]) -> str:
    """Render dashboard HTML from decision data."""
    snapshot = data.get("decision_snapshot", {})
    # Support both key variants:
    # - Phase 6A initial: execution_gate_result / dry_run_execution_result
    # - Phase 6A.1 unified artifact: execution_gate / dry_run_result
    gate_result = data.get("execution_gate_result") or data.get("execution_gate") or {}
    execution_plan = data.get("execution_plan", {})
    dry_run_result = data.get("dry_run_execution_result") or data.get("dry_run_result") or {}

    # Run Header
    as_of = snapshot.get("as_of", "N/A")
    universe_id = snapshot.get("universe_id_or_hash", "N/A")
    
    # Stats Summary
    stats = snapshot.get("stats", {})
    total_candidates = stats.get("total_candidates", 0)
    csp_candidates = stats.get("csp_candidates", 0)
    cc_candidates = stats.get("cc_candidates", 0)
    symbols_evaluated = stats.get("symbols_evaluated", 0)
    total_exclusions = stats.get("total_exclusions", 0)
    
    # Selected Signals
    selected_signals = snapshot.get("selected_signals", []) or []
    selected_count = len(selected_signals)
    
    # Explainability
    explanations = snapshot.get("explanations", []) or []
    explanations_count = len(explanations)
    
    # Execution Gate Result
    gate_allowed = gate_result.get("allowed", False)
    gate_reasons = gate_result.get("reasons", [])
    gate_status_text = "ALLOWED" if gate_allowed else "BLOCKED"
    gate_status_class = "status-allowed" if gate_allowed else "status-blocked"
    
    # Execution Plan
    plan_allowed = execution_plan.get("allowed", False)
    plan_blocked_reason = execution_plan.get("blocked_reason")
    plan_orders = execution_plan.get("orders", [])
    plan_orders_count = len(plan_orders) if plan_orders else 0
    plan_status_text = "ALLOWED" if plan_allowed else "BLOCKED"
    plan_status_class = "status-allowed" if plan_allowed else "status-blocked"
    
    # Dry-Run Result
    dry_run_allowed = dry_run_result.get("allowed", False)
    dry_run_executed_at = dry_run_result.get("executed_at", "N/A")
    dry_run_orders = dry_run_result.get("orders", [])
    dry_run_orders_count = len(dry_run_orders) if dry_run_orders else 0
    dry_run_status_text = "ALLOWED" if dry_run_allowed else "BLOCKED"
    dry_run_status_class = "status-allowed" if dry_run_allowed else "status-blocked"

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ChakraOps Decision Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .section {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 0;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 8px;
        }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}
        .stat-card {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #4CAF50;
        }}
        .stat-label {{
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }}
        .stat-value {{
            font-size: 1.5em;
            font-weight: bold;
            color: #333;
        }}
        .signal-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        .signal-table th {{
            background: #4CAF50;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        .signal-table td {{
            padding: 10px;
            border-bottom: 1px solid #e0e0e0;
        }}
        .signal-table tr:hover {{
            background: #f5f5f5;
        }}
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.9em;
            font-weight: bold;
        }}
        .status-allowed {{
            background: #4CAF50;
            color: white;
        }}
        .status-blocked {{
            background: #f44336;
            color: white;
        }}
        .reason-list {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px;
            margin-top: 10px;
        }}
        .reason-list ul {{
            margin: 5px 0;
            padding-left: 20px;
        }}
        .order-card {{
            background: #e3f2fd;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 4px;
        }}
        .order-header {{
            font-weight: bold;
            color: #1976D2;
            margin-bottom: 8px;
        }}
        .order-details {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            font-size: 0.9em;
        }}
        .order-detail {{
            color: #555;
        }}
        .order-detail strong {{
            color: #333;
        }}
        .explanation-card {{
            background: #f3e5f5;
            border-left: 4px solid #9C27B0;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 4px;
        }}
        .score-breakdown {{
            margin-top: 10px;
            font-size: 0.9em;
        }}
        .score-component {{
            display: inline-block;
            background: white;
            padding: 4px 8px;
            margin: 2px;
            border-radius: 4px;
            border: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <h1>ChakraOps Decision Dashboard</h1>
    
    <!-- Run Header -->
    <div class="section">
        <h2>Run Header</h2>
        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-label">As Of</div>
                <div class="stat-value">{as_of}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Universe ID</div>
                <div class="stat-value">{universe_id}</div>
            </div>
        </div>
    </div>
    
    <!-- Stats Summary -->
    <div class="section">
        <h2>Stats Summary</h2>
        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-label">Total Candidates</div>
                <div class="stat-value">{total_candidates}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">CSP Candidates</div>
                <div class="stat-value">{csp_candidates}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">CC Candidates</div>
                <div class="stat-value">{cc_candidates}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Symbols Evaluated</div>
                <div class="stat-value">{symbols_evaluated}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Exclusions</div>
                <div class="stat-value">{total_exclusions}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Selected Signals</div>
                <div class="stat-value">{selected_count}</div>
            </div>
        </div>
    </div>
    
    <!-- Selected Signals -->
    <div class="section">
        <h2>Selected Signals ({selected_count})</h2>
"""
    
    if selected_signals:
        html += """
        <table class="signal-table">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Symbol</th>
                    <th>Type</th>
                    <th>Strike</th>
                    <th>Expiry</th>
                    <th>Score</th>
                    <th>Bid</th>
                    <th>Ask</th>
                    <th>Mid</th>
                </tr>
            </thead>
            <tbody>
"""
        for selected in selected_signals:
            scored = selected.get("scored", {})
            candidate = scored.get("candidate", {})
            score = scored.get("score", {})
            rank = scored.get("rank", "N/A")
            
            symbol = candidate.get("symbol", "N/A")
            signal_type = candidate.get("signal_type", "N/A")
            strike = candidate.get("strike", "N/A")
            expiry = candidate.get("expiry", "N/A")
            total_score = score.get("total", "N/A")
            bid = candidate.get("bid", "N/A")
            ask = candidate.get("ask", "N/A")
            mid = candidate.get("mid", "N/A")
            
            html += f"""
                <tr>
                    <td>{rank}</td>
                    <td><strong>{symbol}</strong></td>
                    <td>{signal_type}</td>
                    <td>{strike}</td>
                    <td>{expiry}</td>
                    <td>{total_score:.4f if isinstance(total_score, (int, float)) else total_score}</td>
                    <td>{bid}</td>
                    <td>{ask}</td>
                    <td>{mid}</td>
                </tr>
"""
        html += """
            </tbody>
        </table>
"""
    else:
        html += "<p>No selected signals.</p>"
    
    html += f"""
    </div>
    
    <!-- Explainability -->
    <div class="section">
        <h2>Explainability ({explanations_count} explanations)</h2>
"""
    
    if explanations:
        for expl in explanations:
            symbol = expl.get("symbol", "N/A")
            signal_type = expl.get("signal_type", "N/A")
            # Handle SignalType enum serialization
            if isinstance(signal_type, dict):
                signal_type = signal_type.get("value", signal_type.get("name", "N/A"))
            rank = expl.get("rank", "N/A")
            total_score = expl.get("total_score", "N/A")
            components = expl.get("score_components", [])
            policy = expl.get("policy_snapshot", {})
            
            html += f"""
        <div class="explanation-card">
            <div class="order-header">{symbol} {signal_type} (Rank {rank}) - Score: {total_score:.4f if isinstance(total_score, (int, float)) else total_score}</div>
            <div class="score-breakdown">
                <strong>Score Components:</strong>
"""
            if components:
                for comp in components:
                    name = comp.get("name", "N/A")
                    value = comp.get("value", "N/A")
                    weight = comp.get("weight", "N/A")
                    html += f'<span class="score-component">{name}: {value:.3f if isinstance(value, (int, float)) else value} (w={weight:.2f if isinstance(weight, (int, float)) else weight})</span>'
            else:
                html += '<span class="score-component">No components available</span>'
            
            html += f"""
            </div>
            <div style="margin-top: 10px;">
                <strong>Policy:</strong> max_total={policy.get("max_total", "N/A")}, 
                max_per_symbol={policy.get("max_per_symbol", "N/A")}, 
                min_score={policy.get("min_score", "N/A")}
            </div>
        </div>
"""
    else:
        html += "<p>No explanations available.</p>"
    
    html += f"""
    </div>
    
    <!-- Execution Gate Result -->
    <div class="section">
        <h2>Execution Gate Result</h2>
        <div>
            <span class="status-badge {gate_status_class}">
                {gate_status_text}
            </span>
"""
    
    if gate_reasons:
        html += """
            <div class="reason-list">
                <strong>Reasons:</strong>
                <ul>
"""
        for reason in gate_reasons:
            html += f"<li>{reason}</li>"
        html += """
                </ul>
            </div>
"""
    
    html += f"""
        </div>
    </div>
    
    <!-- Execution Plan -->
    <div class="section">
        <h2>Execution Plan ({plan_orders_count} orders)</h2>
        <div>
            <span class="status-badge {plan_status_class}">
                {plan_status_text}
            </span>
"""
    
    if plan_blocked_reason:
        html += f"""
            <div class="reason-list">
                <strong>Blocked Reason:</strong> {plan_blocked_reason}
            </div>
"""
    
    if plan_orders:
        html += """
            <div style="margin-top: 15px;">
"""
        for order in plan_orders:
            symbol = order.get("symbol", "N/A")
            action = order.get("action", "N/A")
            strike = order.get("strike", "N/A")
            expiry = order.get("expiry", "N/A")
            option_right = order.get("option_right", "N/A")
            quantity = order.get("quantity", "N/A")
            limit_price = order.get("limit_price", "N/A")
            
            html += f"""
                <div class="order-card">
                    <div class="order-header">{symbol} {action}</div>
                    <div class="order-details">
                        <div class="order-detail"><strong>Strike:</strong> {strike}</div>
                        <div class="order-detail"><strong>Expiry:</strong> {expiry}</div>
                        <div class="order-detail"><strong>Right:</strong> {option_right}</div>
                        <div class="order-detail"><strong>Quantity:</strong> {quantity}</div>
                        <div class="order-detail"><strong>Limit Price:</strong> ${limit_price:.2f if isinstance(limit_price, (int, float)) else limit_price}</div>
                    </div>
                </div>
"""
        html += """
            </div>
"""
    else:
        html += "<p>No orders in execution plan.</p>"
    
    html += f"""
        </div>
    </div>
    
    <!-- Dry-Run Result -->
    <div class="section">
        <h2>Dry-Run Execution Result</h2>
        <div>
            <span class="status-badge {dry_run_status_class}">
                {dry_run_status_text}
            </span>
            <div style="margin-top: 10px;">
                <strong>Executed At:</strong> {dry_run_executed_at}
            </div>
            <div style="margin-top: 10px;">
                <strong>Orders Executed:</strong> {dry_run_orders_count}
            </div>
        </div>
    </div>
    
</body>
</html>
"""
    
    return html


def generate_dashboard_html(json_file: str, output_html: str = None):
    """Generate static HTML dashboard from JSON file."""
    json_path = Path(json_file)
    data = load_decision_data(json_path)
    html = render_dashboard_html(data)
    
    if output_html is None:
        output_html = json_path.with_suffix(".html")
    else:
        output_html = Path(output_html)
    
    with open(output_html, "w") as f:
        f.write(html)
    
    print(f"Dashboard HTML generated: {output_html}")
    return output_html


def run_dashboard(json_file: str, host: str = "127.0.0.1", port: int = 8000):
    """Run dashboard server (requires FastAPI)."""
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not available. Install with: pip install fastapi uvicorn")
    
    import uvicorn
    
    # Store json_file in closure for route to access
    default_json_file = json_file
    
    app = FastAPI(title="ChakraOps Decision Dashboard")
    
    @app.get("/", response_class=HTMLResponse)
    async def dashboard(json_file_param: str = None):
        """Render decision dashboard from JSON file."""
        # Use json_file from query param if provided, otherwise use closure value
        file_to_load = json_file_param if json_file_param else default_json_file
        json_path = Path(file_to_load)
        try:
            data = load_decision_data(json_path)
            html = render_dashboard_html(data)
            return HTMLResponse(content=html)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error rendering dashboard: {e}")
    
    print(f"Starting dashboard server...")
    print(f"Access at: http://{host}:{port}/?json_file={json_file}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python decision_dashboard.py <json_file> [output_html]")
        sys.exit(1)
    
    json_file = sys.argv[1]
    output_html = sys.argv[2] if len(sys.argv) > 2 else None
    
    if FASTAPI_AVAILABLE:
        run_dashboard(json_file)
    else:
        generate_dashboard_html(json_file, output_html)
