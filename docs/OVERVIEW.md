# Trading Journal — System Overview

**Version:** 1.12.3
**Last Updated:** 2026-03-14
**Status:** Production (Phase 4 complete)

This document is the authoritative single-page description of what the system does, how it
is built, why key decisions were made, and what remains open. It is intended to be shared
with other engineers and LLMs to elicit analysis and feedback. Keep it current as the system
evolves.

---

## 1. Problem Statement

Day traders using Charles Schwab generate CSV activity reports after each session. These
files contain raw fills — individual order executions — that must be stored, correlated, and
analyzed to understand trading performance over time.

The existing **schwab-csv-to-json** sibling project converts raw Schwab CSVs into normalized
NDJSON. This application picks up from there: it ingests that NDJSON (and directly accepts
CSV uploads via web UI), stores everything in PostgreSQL, correlates buy and sell executions
into round-trip trades, calculates P&L using average cost basis, and surfaces the results
through both a web dashboard and a CLI.

The hard problems this application solves:

- **Idempotent re-ingestion.** Traders frequently re-upload the same file after corrections.
  The system must produce identical results whether a file has been uploaded once or ten times.
- **Correct P&L after partial fills.** A single "trade" may involve 4–6 individual execution
  rows at slightly different prices. Average cost basis must be maintained correctly across
  partial opens and closes.
- **Option expiry.** Open option positions that pass their expiration date must be closed
  automatically (long = full loss of premium, short = full retention of premium).
- **Performance at upload time.** With a remote PostgreSQL server and a gunicorn worker timeout
  of 30 seconds, rebuilding all positions after every upload was fatal. Position reprocessing
  is now scoped to only the symbols present in the uploaded file.

---

## 2. Architecture

```
 Schwab CSV file
      │
      ▼
 CsvParser                    ← reads raw Schwab CSV; parses account line (row 1);
      │                          detects sections; normalises columns; emits record dicts
      │
      ▼
 NdjsonRecord (Pydantic)      ← validates each record; extracts option fields;
      │                          generates unique_key for dedup
      │
      ▼
 NdjsonIngester               ← bulk UPSERT into trades table;
      │                          resolves/creates Account records;
      │                          calls TradeCompletionEngine;
      │                          calls PositionTracker (symbol-scoped)
      │
      ├──► trades              (executions / fills)
      │
      ├──► TradeCompletionEngine  ──► completed_trades   (round-trip trades)
      │
      └──► PositionTracker        ──► positions           (running aggregate)

 Web UI (Flask)
      ├── /ingest              upload CSV or NDJSON
      ├── /                    dashboard (metrics, equity curve)
      ├── /trades              paginated completed trades list
      ├── /trades/<id>         trade detail + grail plan link
      ├── /positions           open and closed positions
      ├── /admin/users         user management (admin only)
      ├── /admin/export        annotation export as JSON (admin only)
      ├── /about               release notes accordion
      └── /api/*               JSON API (dashboard, trades)

 CLI (Click via main.py)
      ├── ingest file / batch
      ├── db migrate / status / reset / process-trades
      ├── report trades / positions / dashboard
      ├── pattern annotate / list / performance
      ├── notes add / show / edit
      └── users list / create / deactivate / …
```

---

## 3. Three-Tier Data Hierarchy

This is the central design of the system. Understanding it is required to reason about
any part of the codebase.

```
TIER 1 — trades (executions)
  One row per broker fill. Immutable input data. Never recalculated.
  Source: NDJSON / CSV upload.
  Key fields: unique_key, exec_timestamp, symbol, side, qty, net_price,
              pos_effect ("TO OPEN" / "TO CLOSE"), instrument_type, option_data (JSONB)
  FK: completed_trade_id (nullable until TradeCompletionEngine runs)

TIER 2 — completed_trades (round-trip trades)
  One row per buy→sell (or sell→buy) round trip. Derived from Tier 1.
  Can be fully deleted and rebuilt from the trades table at any time.
  Key fields: entry_avg_price, exit_avg_price, net_pnl, opened_at, closed_at,
              hold_duration, is_winning_trade, trade_type

TIER 3 — positions (running aggregate)
  One row per (user, symbol, instrument_type, option_details). Derived from Tier 1.
  Can be fully deleted and rebuilt at any time.
  Key fields: current_qty, avg_cost_basis, total_cost, realized_pnl,
              opened_at, closed_at
```

**Critical implication:** Tier 2 and Tier 3 are **fully derived**. The only durable
user data is in Tier 1 (`trades`) and in `trade_annotations` (see §5). If `completed_trades`
or `positions` are ever corrupted, running `db process-trades` and position reprocessing
restores them exactly.

---

## 4. Database Schema

### Core tables

| Table | Purpose | Key constraints |
|---|---|---|
| `users` | Auth, multi-user isolation | username UNIQUE, api_key_hash UNIQUE |
| `accounts` | Brokerage accounts per user | (user_id, account_number) UNIQUE |
| `trades` | Individual fills (Tier 1) | (user_id, unique_key) UNIQUE |
| `completed_trades` | Round-trip trades (Tier 2) | user_id FK |
| `trade_annotations` | Manual annotations (pattern, notes, stop) | (user_id, symbol, opened_at) UNIQUE |
| `positions` | Running position aggregate (Tier 3) | (user_id, symbol, instrument_type, option_details, account_id) UNIQUE |
| `setup_patterns` | User-managed dropdown: pattern names | case-insensitive UNIQUE per user |
| `setup_sources` | User-managed dropdown: signal sources | case-insensitive UNIQUE per user |
| `processing_log` | Ingest audit trail | (user_id, file_path, processing_started_at) UNIQUE |
| `ohlcv_price_series` | Future price data (currently unused) | (symbol, timestamp, timeframe) UNIQUE |

### Why `trade_annotations` is a separate table

Annotations (pattern, notes, stop price) are the only data the user enters manually.
The `completed_trades` table is destroyed and rebuilt during `db process-trades`. If
annotations lived on `completed_trades`, every reprocess would delete them.

`trade_annotations` has an FK to `completed_trades` but with `ON DELETE SET NULL`. It
also carries a natural key `(user_id, symbol, opened_at)` so it can be re-linked to a
newly rebuilt `completed_trades` row without losing any annotation data.

### Option representation

Options use a JSONB column (`option_data`) on `trades` and `completed_trades` storing:
`{symbol, exp_date, strike, right, underlying}`. The options multiplier (100x) is applied
at P&L calculation time via `get_contract_multiplier()` in `positions.py`. Options are
identified for uniqueness by `(symbol, instrument_type, exp_date, strike_price, option_type)`.

---

## 5. Key Design Decisions

### 5.1 Average cost basis (not FIFO or LIFO)

All P&L uses weighted average cost. When shares are added to an existing position, a new
average is computed: `(old_total_cost + new_cost) / new_total_qty`. When shares are closed,
P&L = `(exit_price − avg_cost) × qty`.

Chosen for: computational simplicity, platform compatibility, correct behavior on partial
fills. FIFO would require lot tracking which adds significant complexity without meaningful
accuracy gain for the target use case (intraday equities/options).

### 5.2 Idempotent UPSERT ingestion

`NdjsonIngester._insert_records_with_tracking` uses PostgreSQL `INSERT … ON CONFLICT DO UPDATE`
keyed on `(user_id, unique_key)`. Re-uploading the same file updates the existing rows
(timestamps, prices) rather than creating duplicates. Position reprocessing after ingest
rebuilds from scratch, so the final state is always correct regardless of upload history.

`unique_key` is generated in `NdjsonRecord` from a hash of `(exec_time, symbol, side, qty, price)`.

### 5.3 Symbol-scoped position reprocessing

**Before (broken):** every upload called `reprocess_all_positions(user_id)`, which deleted
and rebuilt every position the user has ever had. With a remote PostgreSQL server this
exceeded the gunicorn 30-second worker timeout.

**After (current):** ingestion extracts the set of symbols in the uploaded file and calls
`reprocess_positions_for_symbols(user_id, symbols)`, which touches only those symbols.
The full rebuild (`reprocess_all_positions`) is still available for CLI/admin use.

Both paths share `_rebuild_positions_in_session`, which keeps an in-memory dict of positions
and issues a single bulk UPSERT at the end — no per-trade commits, no per-trade DB reads.

### 5.4 TradeCompletionEngine grouping algorithm

Executions are grouped by `(account_id, symbol, instrument_type)` for equities, or by
`(account_id, symbol, instrument_type, exp_date, strike_price, option_type)` for options.
`account_id` is the outermost key, ensuring fills from different brokerage accounts for
the same symbol are never merged into a single `CompletedTrade`.

Within each group, fills are processed chronologically. A running `open_qty` tracks
the net position. When `open_qty` returns to zero, the group is sealed as a
`CompletedTrade`.

Fills with no account (NDJSON uploads without account info) have `account_id=None` and
group together correctly — Python treats `None` as a valid, comparable dict key.

### 5.5 Grail integration (read-only external DB)

The `grail_files` database (separate PostgreSQL database on the same server) stores
pre-trade JSON plans created by the `save-grail-json` sibling project before a trade is
taken. On the trade detail page, `grail_connector.find_grail_match()` queries
`grail_files` for a record with the same ticker, on the same date, created before
`opened_at`. If found, a "View Trade Plan" button appears. The connection is
fire-and-forget: if `grail_files` is unreachable the page renders normally with no button.

---

## 6. Data Flow: CSV Upload to Database

```
1. User uploads CSV via /ingest (multipart POST)
   └── ingest.py route → CsvParser.parse_file()
       ├── reads row 1: "for 79967586SCHW (Contributory IRA)" → account_number, account_name
       ├── detects section boundaries ("Equities", "Options", etc.)
       ├── normalises column headers via COL_ALIASES
       ├── filters TRIGGERED/REJECTED rows
       └── emits list of record dicts with account_number attached

2. NdjsonIngester.ingest_records(records)
   ├── validates each record via NdjsonRecord (Pydantic)
   │   ├── generates unique_key
   │   ├── parses option fields (exp_date, strike, right)
   │   └── rejects invalid records (logged, not fatal)
   ├── _get_or_create_account() per account_number → accounts.account_id
   ├── bulk UPSERT into trades (INSERT … ON CONFLICT DO UPDATE)
   ├── session.commit()
   ├── TradeCompletionEngine.reprocess_all_completed_trades(user_id)
   │   ├── unlinks all executions from completed_trades
   │   ├── deletes all completed_trades for user
   │   ├── re-groups executions → new CompletedTrade rows
   │   └── re-links trade_annotations via natural key (user_id, symbol, opened_at)
   └── PositionTracker.reprocess_positions_for_symbols(user_id, affected_symbols)
       ├── deletes positions only for uploaded symbols
       ├── loads all historical fills for those symbols (ordered by timestamp)
       ├── rebuilds positions in memory (single-pass, no DB reads)
       ├── bulk UPSERT positions
       └── _expire_worthless_options() — zero-out expired option positions
```

---

## 7. Current Feature Inventory

### Web UI
| Feature | Route | Notes |
|---|---|---|
| Dashboard | `/` | Total P&L, win rate, profit factor, avg win/loss, avg trade, largest win/loss, max win/loss streak, trade counts, equity curve. Defaults to "All time" on load. Account filter dropdown. Profit factor = total winning P&L ÷ \|total losing P&L\|; null when no losers. |
| Trades list | `/trades` | Sort by any column, filter by symbol/date range/account, pagination (per_page persisted in session). Account filter preserved across sort and pagination links. |
| Trade detail | `/trades/<id>` | Execution breakdown, annotation form, prev/next navigation, Grail plan link with copy-to-clipboard |
| Trade annotation | `/trades/<id>/annotate` | Pattern (managed dropdown + inline create), source, stop price, notes |
| Positions | `/positions` | All positions with open/closed status, filter by symbol/account |
| CSV upload | `/ingest` | Drag-and-drop CSV; shows insert/update counts; inline error display |
| Admin: users | `/admin/users` | Create, deactivate, regenerate API key; pill sub-nav to export (admin-only) |
| Admin: export | `/admin/export` | Export trade annotations as JSON (format v2.0); per-account or multi-user selection (admin-only) |
| About | `/about` | Release notes parsed from RELEASE_NOTES.md; Bootstrap accordion; current release badged |
| Settings | `/settings` | User preferences |
| JSON API | `/api/dashboard`, `/api/trades` | For external tooling; dashboard endpoint accepts `?account=` filter |

### CLI
| Command group | Key commands |
|---|---|
| `ingest` | `file`, `batch` (glob), `--dry-run` |
| `db` | `migrate`, `status`, `reset`, `process-trades [--symbol] [--reprocess]` |
| `report` | `trades`, `positions`, `dashboard [--date-range] [--format json]` |
| `pattern` | `annotate`, `list`, `performance` |
| `notes` | `add`, `show`, `edit` |
| `users` | `list`, `create`, `deactivate`, `reactivate`, `make-admin`, `delete`, `regenerate-key` |
| `config` | `setup`, `show`, `validate`, `migrate` |

### Authentication
- Session login (username + password hash) for web UI
- API key (SHA256-hashed, stored in `users.api_key_hash`) for CLI and API
- Admin mode via `ADMIN_MODE_ENABLED=true` env var for initial setup
- All data fully isolated by `user_id` FK on every table

---

## 8. Configuration

Two-tier TOML system designed for `uv tools install` (isolated environments):

```
~/.config/postgres/default.toml    — shared PostgreSQL server credentials
~/.config/trading-journal/config.toml  — app config with named profiles (prod/dev/test)
```

Profiles select the database name. The same PostgreSQL server is used across profiles.
Priority: env vars → profile → app config → shared postgres config → legacy .env → defaults.

The legacy `.env` file still works but prints a deprecation warning. Run
`trading-journal config migrate` to convert.

---

## 9. Infrastructure

- **Web server:** gunicorn (30s worker timeout) behind Nginx, managed by Dokploy
- **Container:** `Dockerfile` + `docker-compose.yml` (bind-mounts source, connects to remote DB); `gunicorn.ctl` socket for graceful reloads
- **Database:** PostgreSQL 14+ on remote server (`192.168.1.249:32768`)
- **Migrations:** Alembic (`alembic/versions/`)
- **Dependency management:** `uv` (`pyproject.toml` + `uv.lock`)
- **Test suite:** pytest (`tests/`)

---

## 10. Known Limitations and Open Problems

### Multi-account support (complete)
The `accounts` table, `CsvParser` account-line parsing, `account_id` FKs on all three
tiers, and web UI account filters on both `/trades` and `/positions` are all implemented.
Trade grouping and position tracking are both account-scoped: fills from different accounts
for the same symbol produce separate `CompletedTrade` and `Position` rows.
The `unique_position_per_user` constraint now includes `account_id`. Null-account positions
(NDJSON uploads without account info) continue to group together correctly via code logic.

### Trade completion is a full rebuild
`TradeCompletionEngine.reprocess_all_completed_trades` always rebuilds all completed trades
for the user, not just affected symbols. This is fast enough currently but will become a
bottleneck at large trade volumes (same class of problem as positions had before §5.3).

### No real-time data
All data is file-import only. There is no connection to live broker APIs or market data
feeds. The `ohlcv_price_series` table exists but is empty — it was designed for future
entry/exit price analysis against market context.

### Single brokerage source
The parser understands Schwab CSV format only. Other brokerages would require a new parser
producing the same `NdjsonRecord` schema.

### Annotation re-linking is best-effort
After a full `completed_trades` rebuild, annotations are re-linked by matching
`(user_id, symbol, opened_at)`. If two trades for the same symbol open at exactly the
same millisecond (unlikely but possible with partial fills), one annotation may attach to
the wrong trade.

---

## 11. File Map (Key Files Only)

```
trading_journal/
├── models.py               SQLAlchemy ORM — all 10 tables
├── ingestion.py            NdjsonIngester — ingest pipeline entry point
├── csv_parser.py           CsvParser — Schwab CSV → record dicts
├── schemas.py              NdjsonRecord pydantic schema + unique_key generation
├── trade_completion.py     TradeCompletionEngine — groups fills into completed trades
├── positions.py            PositionTracker — avg cost basis, bulk UPSERT, option expiry
├── dashboard.py            DashboardEngine — metrics aggregation
├── grail_connector.py      Read-only connector to external grail_files DB
├── config.py               Two-tier TOML config loader
├── database.py             db_manager singleton, session context manager
├── authorization.py        AuthContext — current-user thread-local
├── duplicate_detector.py   Cross-user duplicate detection before ingest
│
└── web/
    ├── __init__.py         Flask app factory
    ├── templates/          Jinja2 templates
    └── routes/
        ├── auth.py         /login, /logout
        ├── dashboard.py    /
        ├── trades.py       /trades, /trades/<id>, annotate, delete, grail-plan
        ├── positions.py    /positions
        ├── ingest.py       /ingest (CSV upload)
        ├── admin.py        /admin/users, /admin/export
        ├── about.py        /about (release notes)
        ├── settings.py     /settings
        └── api.py          /api/*

main.py                     Click CLI entry point
wsgi.py                     gunicorn entry point
alembic/versions/           Migration history
RELEASE_NOTES.md            Release history; parsed by /about route
```

---

## 12. Sibling Projects

| Project | Location | Role |
|---|---|---|
| schwab-csv-to-json | `../schwab-csv-to-json` | Original Schwab CSV → NDJSON converter (now superseded by built-in CsvParser, but still used for NDJSON batch workflows) |
| save-grail-json | separate repo | Writes pre-trade JSON plans to the `grail_files` PostgreSQL database; this app reads them read-only |
