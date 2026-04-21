# Trading Journal — System Overview

**Version:** 1.26.12
**Last Updated:** 2026-04-21
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
      ├── /admin/users                  user management (admin only)
      ├── /admin/market-data            Polygon.io enrichment + OHLCV explorer (admin only)
      ├── /admin/market-data/hg-analysis  HG plan analysis dashboard + batch trigger (admin only)
      ├── /admin/grail-plans            Grail Plan Browser: filter, analyze, batch-analyze (admin only)
      ├── /admin/export                 annotation export as JSON (admin only)
      ├── /journal             timestamped free-form notes (list + create + edit + delete)
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
              pos_effect ("TO OPEN" / "TO CLOSE"), instrument_type (EQUITY/OPTION/FUTURES), option_data (JSONB)
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
| `trade_annotations` | Manual annotations (pattern, notes, stop, atm_engaged, exit_reason, underlying_at_entry) | (user_id, symbol, opened_at) UNIQUE |
| `positions` | Running position aggregate (Tier 3) | (user_id, symbol, instrument_type, option_details, account_id) UNIQUE |
| `setup_patterns` | User-managed dropdown: pattern names | case-insensitive UNIQUE per user |
| `setup_sources` | User-managed dropdown: signal sources | case-insensitive UNIQUE per user |
| `processing_log` | Ingest audit trail | (user_id, file_path, processing_started_at) UNIQUE |
| `ohlcv_price_series` | 1-min and daily OHLCV bars fetched from Polygon.io; cached to avoid redundant API calls; includes `vwap` column | (symbol, timestamp, timeframe) UNIQUE |
| `hg_market_data_requests` | Audit trail of bar-fetch operations tied to a grail plan: symbol, timeframe, fetch window, status, bar counts, window rule | (user_id, grail_plan_id, timeframe, fetch_start_at, fetch_end_at) UNIQUE |
| `hg_analysis_results` | Versioned evaluation results per HG plan: entry touch type, TP1/TP2 reached, MFE/MAE, bars-to-entry, linked-trade comparison | (hg_market_data_request_id, analysis_version) UNIQUE |
| `grail_plan_analyses` | Plan-centric zone-based analysis results from Grail Plan Browser: entry/stop/TP1 zone touch, outcome, fetch metadata, bars_expected | (grail_plan_id, analysis_version) effectively UNIQUE per user; user_id FK |
| `journal_notes` | Free-form trader notes (not trade-linked): title, body (markdown), timestamps | note_id PK; user_id FK |

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

Executions are grouped by `(account_id, symbol, instrument_type)` for equities, by
`(account_id, symbol, instrument_type, exp_date, strike_price, option_type)` for options,
or by `(account_id, symbol, instrument_type, contract_expiry)` for futures.
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

As of April 2026 `grail_files` carries pre-extracted columns for the key plan levels
(`entry_direction`, `entry_low`, `entry_high`, `stop_low`, `stop_high`, `tp1_low`,
`tp1_high`, `tp2_low`, `tp2_high`). `grail_connector` uses these directly: direction
filtering in `find_grail_match` and `batch_grail_coverage` uses the `entry_direction`
column instead of navigating JSONB; `list_grail_candidates` returns `entry_low`/`entry_high`
so callers have the entry zone without parsing `json_content`.

### 5.6 HG plan analysis pipeline

"HG" (Historical Grail) is the system for evaluating pre-trade plans against actual
1-minute bar data after the fact. The pipeline has three stages:

**Stage 1 — Hydration** (`hg_hydration.py: hydrate_hg_plan`): Looks up the grail plan in
`grail_files`, computes a fetch window (plan creation time − 30m through + 90m, extended
to linked trade exit when applicable), fetches the full bar range from Polygon.io via
`MassiveClient.fetch_window_bars`, upserts bars into the shared `ohlcv_price_series` cache,
and writes an `HgMarketDataRequest` row (pending → success/partial/failed). Idempotent:
an existing successful request for the same window is returned as-is.

**Stage 2 — Evaluation** (`hg_evaluator.py: evaluate_hg_plan`): Reads the hydrated bars,
snapshots plan parameters (side, entry zone, targets, stop) from `grail_files`, runs a
deterministic bar-scan, and writes a versioned `HgAnalysisResult`. Evaluated fields:
entry-zone touch type (`never`/`top_of_zone`/`in_zone`/`bottom_of_zone`/`through_zone`),
TP1/TP2 reached with bar counts, MFE/MAE, and linked-trade comparison (actual entry/exit
vs plan zone). Results are keyed by `analysis_version` so logic can evolve without
destroying historical rows.

Parameter extraction (`_load_plan_params`) uses the pre-extracted columns where possible:
`entry_low`/`entry_high` (always underlying prices regardless of asset type) for the entry
zone; for **equity** plans, `stop_low`/`stop_high` and `tp1_low`/`tp1_high`/`tp2_low`/
`tp2_high` with direction-aware bound selection (long stop → `stop_high` / tighter upper
bound; long tp1 → `tp1_low` / conservative lower bound; mirrored for short). For
**option** plans, stop and TP still read from JSON `stock_price_range` because the
pre-extracted columns hold option premium prices, not the underlying prices the bar scan
requires. Falls back to JSON for any NULL column (pre-migration rows).

**Futures data**: Standard Polygon.io equity endpoint returns HTTP 200 with 0 bars for
futures tickers — indistinguishable from throttling. `MassiveClient.fetch_futures_window_bars`
calls the dedicated Massive futures endpoint (`api.massive.com/futures/v1/aggs/`), which
returns `{"status": "NOT_AUTHORIZED"}` in the JSON body (HTTP 200) when the subscription
does not cover futures. This is detected and surfaced as `fetch_status="no_subscription"`,
which short-circuits the bar scan (skipping `_load_bars`) and sets `outcome="no_data"`. The
Grail Plan Browser shows a blue "no subscription" badge. The plan is excluded from the
"already analyzed" filter on subsequent batch runs (the `no_data` outcome is not treated as
final) so it will be retried automatically if the subscription is upgraded.

**Stage 3 — Display**: Trade detail page shows an "HG Plan Analysis" card when an
`HgAnalysisResult` exists for the linked grail plan. Admin → HG Analysis page lists all
analyses and provides a "Run Batch" button that processes up to 20 unanalyzed trades.

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
| Trades list | `/trades` | Sort by any column, filter by symbol/date range/account, pagination (per_page persisted in session). Account filter preserved across sort and pagination links. Bulk delete: "Select to Delete" mode enables row checkboxes and a "Select All" toggle; confirms then permanently deletes selected trades, their executions, and their annotations, and reprocesses affected positions. |
| Trade detail | `/trades/<id>` | Execution breakdown, annotation form, prev/next navigation, Grail plan link with copy-to-clipboard. When an `HgAnalysisResult` exists for the linked grail plan, an "HG Plan Analysis" card shows entry touch type, TP1/TP2 outcome, MFE/MAE, and actual vs plan comparison. "Analyze HG Plan" / "Re-analyze" button triggers hydration + evaluation inline. |
| Trade annotation | `/trades/<id>/annotate` | Pattern (managed dropdown + inline create), source, stop price, notes |
| Positions | `/positions` | All positions with open/closed status, filter by symbol/account |
| CSV upload | `/ingest` | Drag-and-drop Schwab CSV, NinjaTrader `-exec.csv`, or NDJSON; file format auto-detected; shows insert/update counts; inline error display |
| Admin: users | `/admin/users` | Create, deactivate, regenerate API key; pill sub-nav to export (admin-only) |
| Admin: market data | `/admin/market-data` | Three tabs: (1) list option trades missing `underlying_at_entry` with one-click Polygon.io enrichment; (2) fetch 1m/5m/15m OHLCV bars for any symbol and date range; (3) Explore OHLCV — summary stats, HG plan coverage table, schema reference, free-form SELECT query box (500-row cap). Admin-only. |
| Admin: HG analysis | `/admin/market-data/hg-analysis` | Lists all `HgMarketDataRequest` rows with fetch status and linked `HgAnalysisResult` outcomes. "Run Batch (up to 20)" triggers hydration + evaluation for all unanalyzed grail-linked trades. Admin-only. |
| Admin: Grail Plan Browser | `/admin/grail-plans` | Browse and analyze grail plans directly from the `grail_files` DB. Filter by symbol, date range, asset type. Per-plan "Analyze" / "Re-analyze" buttons. Configurable batch analyzer: enter a count, click "Analyze Next N" — SSE streams per-plan results; client-side countdown handles the 60s inter-batch wait (no long-lived connection held open); rate-limited or `no_data` plans are retried on the next batch. Outcome badges: success, failure, inconclusive, no entry, no data, no subscription. Aggregate stats (entry reached %, success/failure/inconclusive %). Admin-only. |
| Admin: export | `/admin/export` | Export all manually entered data as JSON (format v3.0): trade annotations (grouped by account) + journal notes. Per-user selection. Natural keys documented in `export_metadata.schema` for re-import. Admin-only. |
| Journal | `/journal` | Timestamped free-form notes (EasyMDE markdown editor, title optional). List shows newest first with snippet. Not trade-linked. Included in export. |
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
All data is file-import only. There is no connection to live broker APIs. Historical
OHLCV bars are fetched on demand from Polygon.io (`market_data.py`) and cached in
`ohlcv_price_series`. `underlying_at_entry` on `trade_annotations` is auto-populated
for option trades on every CSV upload (when `MASSIVE_API_KEY` is set), and can also
be backfilled manually via Admin → Market Data. HG plan analysis (TP1/TP2 reach,
MFE/MAE, entry touch type) is implemented via the HG pipeline (§5.6). VIX context
analysis is not yet implemented.

### 5.7 Grail Plan Browser analysis pipeline

`grail_analyzer.py: run_grail_plan_analysis()` is the plan-centric counterpart to the
trade-linked HG pipeline (§5.6). Instead of starting from a matched trade, it starts from
a `grail_files` plan ID directly. It is used exclusively by the Admin → Grail Plan Browser.

**Flow**: look up plan in `grail_files` → compute fetch window (plan_created_at − 90m
through + 120m) → fetch 1m bars via `MassiveClient` (equity) or `fetch_futures_window_bars`
(futures, which returns `no_subscription` when the Polygon subscription lacks futures
coverage) → upsert into `ohlcv_price_series` → run zone-based bar scan → write
`GrailPlanAnalysis` row. Idempotent: re-runs only if outcome is `no_data` or `force=True`.

**Outcome values** (`grail_plan_analyses.outcome`):
- `no_data` — bars unavailable; safe to retry
- `no_entry` — bars available but entry zone never touched
- `success` — entry zone touched, TP1 zone hit before stop zone
- `failure` — entry zone touched, stop zone hit before TP1
- `inconclusive` — entry zone touched, neither TP1 nor stop reached in window
- `invalid` — plan lacks required zone fields (entry/stop/TP1 low+high all present is required)

`bars_expected` is computed by counting 1-minute NYSE market-hours slots in the fetch
window (`expected_market_bars()`) so partial-data fetches can be distinguished from
complete ones (when `bars_fetched < bars_expected`).

---

### Grail Plan Browser batch: client-side wait architecture
The batch analyzer avoids long-lived SSE connections (which nginx would drop at
`proxy_read_timeout`, default 60s) by keeping each HTTP request short: the server
processes one sub-batch of up to 5 plans and closes immediately, returning `elapsed_secs`.
The client computes `waitSecs = max(1, ceil(62 − elapsed_secs))` and uses `setInterval`
for the countdown — no open connection is held during the wait. A fresh HTTP POST starts
the next sub-batch. Plans with `outcome='no_data'` are excluded from the "already analyzed"
set so they are retried on subsequent batches.

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
├── models.py               SQLAlchemy ORM — all 14 tables
├── ingestion.py            NdjsonIngester — ingest pipeline entry point
├── csv_parser.py           CsvParser — Schwab CSV → record dicts
├── ninjatrader_parser.py   NinjaTraderParser — NinjaTrader exec CSV → record dicts (FUTURES)
├── schemas.py              NdjsonRecord pydantic schema + unique_key generation
├── trade_completion.py     TradeCompletionEngine — groups fills into completed trades
├── positions.py            PositionTracker — avg cost basis, bulk UPSERT, option expiry
├── dashboard.py            DashboardEngine — metrics aggregation
├── market_data.py          MassiveClient (Polygon.io); enrich_missing_underlying_prices; enrich_trades_by_ids; fetch_window_bars; fetch_futures_window_bars
├── hg_hydration.py         hydrate_hg_plan() — fetch bars for a grail plan → ohlcv_price_series + HgMarketDataRequest
├── hg_evaluator.py         evaluate_hg_plan() — bar-scan evaluator → HgAnalysisResult
├── grail_analyzer.py       run_grail_plan_analysis() — combined hydrate+evaluate entry point used by Grail Plan Browser batch; routes FUTURES asset_type to fetch_futures_window_bars
├── grail_connector.py      Read-only connector to external grail_files DB; list_grail_plans, fetch_grail_plan_full, find_grail_match, batch_grail_coverage
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
        ├── trades.py       /trades, /trades/<id>, annotate, delete, grail-plan, hg-analyze
        ├── positions.py    /positions
        ├── ingest.py       /ingest (CSV upload)
        ├── admin.py        /admin/users, /admin/market-data, /admin/market-data/hg-analysis, /admin/market-data/hg-batch, /admin/grail-plans, /admin/export
        ├── journal.py      /journal — list, create, detail/edit, delete
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
| save-grail-json | separate repo | Writes pre-trade JSON plans to the `grail_files` PostgreSQL database; this app reads them read-only. April 2026: added pre-extracted columns `entry_low/high`, `stop_low/high`, `tp1_low/high`, `tp2_low/high`, `entry_direction`; corrected `entry_price` to source from `ideal_zone.mid`. |
