# Robinhood MCP Tool Classification (R52)

Source: live Cursor MCP server `user-robinhood-trading` (`https://agent.robinhood.com/mcp/trading`), inspected 2026-08-10.

**Never invoke WRITE tools from ChakraOps.** Cursor discovery/validation may use READ tools only.

## READ (allowlisted)

get_accounts, get_portfolio, get_equity_positions, get_option_positions, get_equity_orders, get_option_orders, get_equity_quotes, get_option_quotes, get_option_chains, get_option_instruments, get_option_historicals, get_equity_fundamentals, get_equity_historicals, get_equity_price_book, get_equity_tax_lots, get_equity_technical_indicators, get_equity_tradability, get_financials, get_index_historicals, get_index_quotes, get_indexes, get_earnings_calendar, get_earnings_results, get_option_level_upgrade_info, get_option_watchlist, get_pnl_trade_history, get_popular_watchlists, get_realized_pnl, get_scanner_filter_specs, get_scans, get_watchlist_items, get_watchlists, search

## Explicitly excluded from production read allowlist (R61)

`review_equity_order`, `review_option_order` — order preview/simulation surface not required for portfolio reads. Fail-closed unless a future explicit preview feature is accepted.

## WRITE (denied)

place_equity_order, place_option_order, cancel_equity_order, cancel_option_order, cancel_option_exercise, exercise_option, add_to_watchlist, add_option_to_watchlist, remove_from_watchlist, remove_option_from_watchlist, create_watchlist, update_watchlist, create_scan, update_scan_config, update_scan_filters, run_scan, follow_watchlist, unfollow_watchlist

## Special

| Tool | Classification | Notes |
|------|----------------|-------|
| mcp_auth | NOT allowlisted for app broker client | Cursor/host OAuth helper; production uses independent token env/file |

## Account aliases (mask full numbers)

| Alias | Role |
|-------|------|
| acct_individual | Individual margin (default trading) |
| acct_ira_roth | Roth IRA |
| acct_agentic | Agentic — never used for execution |

Full account numbers must not appear in commits, evidence ZIPs, or unmasked API payloads.
