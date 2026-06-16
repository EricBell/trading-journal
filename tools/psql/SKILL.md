# Skill: psql — Database Query Tool

## When to use

Use this tool whenever you need to inspect live database state to diagnose an issue:
- Checking whether records exist in a table
- Verifying foreign key linkages (e.g. `completed_trade_id` on `trades`)
- Counting or aggregating data to understand system state
- Confirming that a migration or reprocessing step had the expected effect

Do NOT use this tool for writes (`INSERT`, `UPDATE`, `DELETE`) unless the user has explicitly asked for a direct database fix. Prefer fixing data through the application's own pipelines.

## How to invoke

```bash
uv run tools/psql/psql.py "<SQL>"
```

Run this via the Bash tool from the project root. The `.env` file is loaded automatically.

## Parameters

- **Positional**: the SQL string. Use double-quoted outer string and single quotes inside SQL.
- **`--format json`**: use when you need to parse the result programmatically or display structured data.
- **`--limit N`**: override the default 500-row cap.

## Diagnostic query patterns

### Check if records exist for a symbol
```bash
uv run tools/psql/psql.py "SELECT trade_id, side, pos_effect, spread_order_tag, completed_trade_id, exec_timestamp, strike_price, option_type FROM trades WHERE symbol = 'XYZ' ORDER BY exec_timestamp"
```

### Find spread trades that TCE did not match
```bash
uv run tools/psql/psql.py "SELECT symbol, spread_order_tag, count(*) FROM trades WHERE spread_order_tag IS NOT NULL AND completed_trade_id IS NULL GROUP BY symbol, spread_order_tag"
```

### Check completed trades for a symbol
```bash
uv run tools/psql/psql.py "SELECT completed_trade_id, symbol, trade_type, net_pnl, opened_at, closed_at, option_details FROM completed_trades WHERE symbol = 'XYZ' ORDER BY opened_at DESC"
```

### Inspect positions for a symbol
```bash
uv run tools/psql/psql.py "SELECT position_id, symbol, current_qty, avg_cost_basis, realized_pnl, opened_at, closed_at FROM positions WHERE symbol = 'XYZ'"
```

## Notes

- First run downloads dependencies into uv's cache (~2–3 seconds). Subsequent runs are instant.
- The tool is read-only by convention. The database user has full privileges, so be deliberate.
- Results cap at 500 rows by default; use `--limit` or add `LIMIT` to the SQL to adjust.
