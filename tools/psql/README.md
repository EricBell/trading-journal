# psql — Trading Journal Database Query Tool

A self-contained CLI for running SQL queries against the trading-journal PostgreSQL database. Uses `uv run` with inline script dependencies — no project virtualenv is modified and nothing is installed permanently.

## Requirements

- `uv` must be installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A `.env` file in the project root with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

Dependencies (`psycopg2-binary`, `python-dotenv`, `tabulate`) are fetched and cached by `uv` on first run.

---

## Usage

```bash
# SQL as positional argument (most common)
uv run tools/psql/psql.py "SELECT * FROM trades LIMIT 5"

# Pipe SQL from stdin
echo "SELECT count(*) FROM trades" | uv run tools/psql/psql.py

# Here-doc for multi-line queries
uv run tools/psql/psql.py "
  SELECT symbol, count(*) AS fills
  FROM trades
  WHERE exec_timestamp::date = CURRENT_DATE
  GROUP BY symbol
  ORDER BY fills DESC
"
```

---

## Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `sql` | — | stdin | SQL to execute |
| `--format` | `-f` | `table` | Output format: `table`, `csv`, `json` |
| `--limit` | `-l` | `500` | Auto-applied row cap on SELECT queries (skipped if query already has LIMIT) |
| `--host` | — | `DB_HOST` | Override PostgreSQL host |
| `--port` | — | `DB_PORT` | Override PostgreSQL port |
| `--dbname` | — | `DB_NAME` | Override database name |
| `--user` | — | `DB_USER` | Override database user |
| `--password` | — | `DB_PASSWORD` | Override database password |

Connection flags override `.env` values but are optional — the `.env` file is almost always sufficient.

---

## Output formats

**table** (default) — human-readable ASCII table via `tabulate`:
```
+----------+--------+
| symbol   | fills  |
|----------+--------|
| SPY      | 42     |
| QQQ      | 17     |
+----------+--------+

(2 rows)
```

**json** — array of objects, suitable for piping to `jq`:
```bash
uv run tools/psql/psql.py --format json "SELECT * FROM completed_trades LIMIT 2" | jq '.[].symbol'
```

**csv** — header row + data rows, suitable for import into spreadsheets.

---

## Examples

```bash
# All SPCX trades with spread tags and completed-trade linkage
uv run tools/psql/psql.py "
  SELECT trade_id, side, pos_effect, spread_order_tag, completed_trade_id,
         exec_timestamp::date AS date, strike_price, option_type, exp_date
  FROM trades WHERE symbol = 'SPCX' ORDER BY exec_timestamp
"

# Trades missing completed_trade_id (not processed by TCE)
uv run tools/psql/psql.py "
  SELECT symbol, count(*) AS unlinked
  FROM trades
  WHERE completed_trade_id IS NULL AND event_type = 'fill'
  GROUP BY symbol ORDER BY unlinked DESC
"

# Recent completed trades
uv run tools/psql/psql.py "
  SELECT completed_trade_id, symbol, trade_type, net_pnl, opened_at::date
  FROM completed_trades ORDER BY opened_at DESC LIMIT 20
"
```
