## v1.25.2 - 2026-04-07

### Internal
- **grail_files schema update** — Accounts for new pre-extracted columns added by `save-grail-json` (`entry_low`, `entry_high`, `stop_low`, `stop_high`, `tp1_low`, `tp1_high`, `tp2_low`, `tp2_high`, `entry_direction`). The HG evaluator now reads these columns directly for equity plans instead of navigating JSONB at query time. Option plans continue to use `stock_price_range` from JSON for stop/TP (underlying prices, not option premium). Direction filtering in `batch_grail_coverage` and `find_grail_match` also simplified to use the `entry_direction` column. `list_grail_candidates` now returns `entry_low`/`entry_high` for zone display without JSON parsing.

---

## v1.25.1 - 2026-04-01

### Bug Fixes
- **Grail plan "Skip" action** — when candidates exist but no plan is matched, a **Skip** button now appears alongside "Select Plan". Clicking it records the deliberate choice to use no plan (`grail_plan_rejected = true`). Previously, the Reject button only appeared when a plan was already matched.
- **Trades list indicator for skipped plans** — `grail_plan_rejected = true` now shows `!` in the trades list (decision made) instead of blank. Blank is now reserved strictly for trades where no grail plan candidates exist at all.

---

## v1.25.0 - 2026-04-01

### New Features
- **Grail plan indicator column on trades list** — A narrow column between ID and Symbol shows the grail plan status for each trade at a glance:
  - `!` (cyan) — a plan is matched (auto-matched by direction or manually selected)
  - `?` (yellow) — grail plans exist for that ticker/day but none is currently matched
  - blank — no grail plans available for that ticker/day, or match was explicitly rejected
  - Status is computed in a single batch query per page load (one round-trip to grail_files regardless of page size).

---

## v1.24.0 - 2026-04-01

### New Features
- **Grail plan direction filtering** — Auto-matching now filters by trade direction (`LONG`/`SHORT`) when querying the grail_files database. A SHORT plan will no longer be matched to a LONG trade and vice versa when multiple plans exist for the same ticker on the same day.
- **Manual grail plan override** — Trade detail page now shows grail plan controls:
  - **Change Plan / Select Plan** — expands an inline candidate list of all grail plans for that ticker on the trade date, each showing time, direction (LONG/SHORT badge), and asset type. Click **Select** to pin a specific plan.
  - **Reject** — explicitly marks the trade as having no matching plan; suppresses auto-matching.
  - **Reset** — clears any override and re-enables direction-filtered auto-matching.
  - A "manual" badge appears when a plan is pinned; "No plan (manually set)" badge when rejected.
  - HG analysis respects the manual override — the "Analyze HG Plan" button uses the pinned plan instead of re-running auto-match.

### Database Migration
- `trade_annotations`: added `grail_plan_id` (integer, nullable) and `grail_plan_rejected` (boolean, default false).
- Run `trading-journal db migrate` to apply.

---

## v1.23.0 - 2026-03-30

### New Features
- **OHLCV Explorer** — New "Explore OHLCV" sub-tab on Admin → Market Data. Provides a read-only data exploration interface for the `ohlcv_price_series` table:
  - **Summary stats** — total bar count, distinct symbol count, earliest/latest bar date, row counts by timeframe.
  - **HG Plan Coverage table** — one row per `hg_market_data_requests` entry (newest first), showing symbol, grail plan ID, timeframe, fetch window, bars stored, status badge, and whether an `HgAnalysisResult` exists.
  - **Schema Reference** — collapsible reference card showing all columns and types for both `ohlcv_price_series` and key columns of `hg_market_data_requests`.
  - **SQL Query box** — free-form SELECT query textarea (SELECT-only enforced server-side; multi-statement blocked) with results table capped at 500 rows.
  - Pre-filled starter query JOINs bars back to their source HG plan.

---

## v1.22.0 - 2026-03-29

### New Features
- **HG plan analysis UI (Phase 4)** — Full linked-trade comparison view and batch backfill.
  - **Trade detail page** — When a grail plan is linked to a trade, an "HG Plan Analysis" card appears at the bottom. It shows: entry zone touch type (badge: `top of zone` / `in zone` / `bottom of zone` / `through zone` / `never touched`), TP1/TP2 reached with bar counts, MFE/MAE, and a trade-vs-plan comparison (actual fill vs zone, actual exit vs TP1). A single "Analyze HG Plan" button (or "Re-analyze") triggers bar hydration + evaluation and redirects back with results shown immediately.
  - **Admin → HG Analysis** — New admin page (`/admin/market-data/hg-analysis`) lists all past HG analyses with fetch status, entry touch, TP1/TP2 outcome, MFE/MAE, and a link to the associated trade. A "Run Batch (up to 20)" button iterates all trades, finds grail matches, and runs hydration + evaluation for any not yet analyzed. "HG Analysis" tab added to all admin nav pills.

---

## v1.21.0 - 2026-03-29

### New Features
- **HG plan evaluator (Phase 3)** — `trading_journal/hg_evaluator.py` adds `evaluate_hg_plan(request_id)`. Reads 1-minute bars from `ohlcv_price_series` for an already-hydrated request, runs a deterministic bar-scan, and writes a versioned row to `hg_analysis_results`. Evaluated fields include: entry zone touch (with type classification: `never` / `top_of_zone` / `in_zone` / `bottom_of_zone` / `through_zone`), TP1/TP2 reached (checked only on bars after the entry bar), MFE/MAE with timestamps, `bars_to_entry`, `bars_from_entry_to_tp1/tp2`, and linked-trade comparison prices. Plan parameters (zone, targets, stop) are snapshotted at eval time so results remain stable if grail plan data changes. All prices use `stock_price_range` when present (option plans store option premium in `price_range` but underlying prices in `stock_price_range`). Idempotent: an existing result for the same `(request_id, analysis_version)` is returned as-is.

---

## v1.20.0 - 2026-03-29

### New Features
- **HG bar hydration (Phase 2)** — `trading_journal/hg_hydration.py` adds `hydrate_hg_plan(user_id, grail_plan_id, completed_trade_id=None, timeframe='1m')`. Looks up the grail plan from `grail_files`, computes the fetch window (plan_time − 30m through plan_time + 90m, extended to linked trade exit when applicable), fetches the full bar range from Massive/Polygon in a single API call, upserts bars into the shared `ohlcv_price_series` cache, and records the request lifecycle in `hg_market_data_requests` (pending → success/partial/failed). Idempotent: a successful request for the same window is returned as-is; failed/partial requests are retried. `MassiveClient` gains a new `fetch_window_bars(symbol, from_ts, to_ts, timeframe)` method that fetches a wide time window (vs the existing narrow ±3-minute fetch).

---

## v1.19.0 - 2026-03-29

### New Features
- **HG historical analysis schema (Phase 1)** — Two new tables added via Alembic migration:
  - `hg_market_data_requests` — audit trail of bar-fetch requests for a given HG plan (symbol, timeframe, window, status, bar counts, provider metadata).
  - `hg_analysis_results` — versioned, deterministic evaluation results per HG: entry-zone touch type (`never`/`top_of_zone`/`in_zone`/`bottom_of_zone`/`through_zone`), TP1/TP2 reached, MFE/MAE with timestamps, bars-to-entry, and linked-trade comparison hooks. Results are stored, not live-computed, and keyed by `analysis_version` so logic can evolve without losing historical rows.
  - Raw bars continue to live in the shared `ohlcv_price_series` cache (unchanged).

---

## v1.18.2 - 2026-03-28

### Improvements
- **ohlcv_price_series** — Added `vwap` column (`NUMERIC(18,8)`) to the market data table.

---

## v1.18.1 - 2026-03-27

### Improvements
- **Nav "Tools" dropdown** — Upload CSV, Settings, and Admin are now grouped under a single "Tools" dropdown in the navbar, reducing top-level clutter. Admin only appears for admin users, separated by a divider.

---

## v1.18.0 - 2026-03-27

### New Features
- **NinjaTrader futures ingestion** — Upload NinjaTrader executions CSV files (`-exec.csv`) via the existing `/upload` page. The file format is auto-detected; Schwab and NinjaTrader files can be mixed in a single upload. Parses `MES JUN26`-style instrument names into a root symbol (`MES`) plus contract expiry date; supports futures contracts from multiple brokers (MES, ES, NQ, MNQ, YM, CL, GC, and more). Per-contract P&L multipliers are applied correctly (e.g. MES = $5/point). Entry/exit prices are stored as index points so the trades list shows recognisable levels (e.g. 6590.50) rather than contract notional. Contract months are kept separate for position grouping (JUN26 and SEP26 are independent positions). New Alembic migration expands the `instrument_type` constraint to include `FUTURES`.
- **Bulk delete trades** — The trades list now has a "Select to Delete" button. Clicking enters selection mode: row-level checkboxes appear, a "Select All" toggle appears in the header, and selected rows highlight. A "Delete Selected (N)" button is enabled once at least one trade is checked. Pressing it shows a confirmation dialog then permanently deletes the selected completed trades, their underlying executions, and their annotations, and reprocesses positions for affected symbols. Single-trade delete (on the trade detail page) is now available to all logged-in users rather than admins only.

---

## v1.17.0 - 2026-03-19

### New Features
- **Journal** — Timestamped free-form notes, independent of any trade. Accessible via the new "Journal" nav item (between Settings and About). Supports markdown via the EasyMDE editor (same as trade notes). Each note has an optional title; the list shows newest first with a body snippet and timestamp. Notes can be created, edited, and deleted.
- **Journal notes included in export** — Admin → Export now includes all journal notes per user in the downloaded JSON (format v3.0). Notes are exported at the user level alongside trade annotations. `export_metadata.schema` documents the natural keys for re-import: `["username", "symbol", "opened_at"]` for annotations and `["username", "created_at"]` for notes.

---

## v1.16.13 - 2026-03-18

### Bug Fixes
- "Resolve Option Trades" enrichment no longer silently swallows failures. The route is now synchronous — it runs the API calls inline and immediately flashes a specific success/warning/danger message covering all outcomes: enriched, failed (no price data), unavailable (too old for API plan), API key not set, and unexpected exceptions. Previously the result was stored in an in-memory dict by a background thread and only shown if the user happened to refresh at the right moment; after a container restart or a timing race the result was simply lost.

---

## v1.16.12 - 2026-03-18

### Bug Fixes
- Market Data enrichment result banner and fetch error banner showed literal `&#9888;` / `&#9989;` / `&#10060;` text instead of emoji icons — Jinja2 auto-escapes string literals so HTML entities in `{{ }}` expressions are never interpreted. Replaced with direct Unicode characters (⚠️ ✅ ❌).

---

## v1.16.11 - 2026-03-18

### Bug Fixes
- Trade annotations (setup pattern, notes, stop price, etc.) were appearing blank after a CSV re-import because `reprocess_all_completed_trades` deleted and rebuilt `completed_trades` rows, leaving annotation FKs NULL. Annotations were only re-linked lazily when a user opened a trade detail page, so the trades list showed them as empty. Fixed by eagerly re-linking all orphaned annotations to their new `completed_trade_id` (matched on the natural key `user_id / symbol / opened_at`) immediately after the rebuild.

---

## v1.16.10 - 2026-03-16

### Improvements
- Admin → Market Data "Fetch Bars" tab now has a 1m / 5m / 15m timeframe selector; selected timeframe is shown as a badge on the result card.
- Background enrichment result is now persisted in memory and surfaced as a success/warning/error banner on the next page load, replacing the previous "refresh in ~30s" flow.
- Removed debug prints from the enrichment thread; errors are now captured and displayed in the result banner rather than silently logged.

---

## v1.16.8 - 2026-03-16

### Debug
- Log Polygon 403 response body to identify plan/rate-limit errors.

---

## v1.16.7 - 2026-03-16

### Debug
- Added trace prints to enrichment thread and `enrich_trades_by_ids` to diagnose silent failures.

---

## v1.16.6 - 2026-03-16

### Bug Fixes
- Market Data "Resolve Option Trades" panel: "Opened At" times now display correctly in ET instead of being shifted 4–5 hours early (timestamps were stored as naive ET but incorrectly treated as UTC during display).
- Polygon API enrichment now fetches bars at the correct UTC time — fixes the root cause of `unavailable` results when the trades were actually within the free-tier coverage window.
- Added daily-bar fallback when 1-minute bars return 403 or empty results, improving coverage for older trades on the free tier.

---

## v1.16.5 - 2026-03-16

### Bug Fixes
- Trade detail page: Save button is now disabled on load and re-disabled after a successful save; it enables only when a field has been changed.

---

## v1.16.4 - 2026-03-15

### Improvements
- Both enrichment paths (upload auto-enrich and admin manual enrich) are now fully non-blocking — the page responds immediately and enrichment runs in a background thread.

---

## v1.16.3 - 2026-03-15

### Bug Fixes
- Replaced raw `HTTP Error 403: Forbidden` with a specific, actionable message when the Polygon.io API key is invalid or rate-limited.

---

## v1.16.2 - 2026-03-15

### Improvements
- Admin → Market Data page reorganized into two clearly named tabs: **Enrich Underlying Prices** and **Fetch 15-min Bars**.

---

## v1.16.1 - 2026-03-15

### Improvements
- Removed artificial sleep from `enrich_trades_by_ids` — 4 sequential Polygon calls complete in ~5–15 s under the free-tier rate limit without it.
- Gunicorn timeout raised to 120 s to cover worst-case enrichment latency (requires container rebuild).

---

## v1.16.0 - 2026-03-15

### New Features
- Admin → Market Data now shows a card listing all option trades missing `underlying_at_entry`, with a one-click button to enrich them via Polygon.io.

---

## v1.15.0 - 2026-03-15

### Bug Fixes
- Stop price input now enforces `min="0.0001"` so the browser rejects negative values.
- Grail stop is only used as a placeholder when it is a valid positive number, eliminating the spurious `-0.01` that was coming from malformed grail plan JSON.

---

## v1.14.4 - 2026-03-15

### Bug Fixes
- Fixed annotation route to handle a null trade entry price without raising a server error.
- Corrected template rendering for trade entry display.

---

## v1.14.3 - 2026-03-15

### Bug Fixes
- Fixed broken annotation route after earlier template refactor (required container restart).

---

## v1.14.1 - 2026-03-15

### Bug Fixes
- `underlying_at_entry` field now accepts null/blank values without validation error on the annotation form.

---

## v1.14.0 - 2026-03-15

### New Features
- **Market data enrichment (Polygon.io / MASSIVE)** — New `MassiveClient` reads `MASSIVE_API_KEY` from the environment; if absent, enrichment is silently disabled and the upload flow is unaffected.
- `get_underlying_close_at(symbol, ts)` — fetches the 1-min OHLCV bar closest to a fill timestamp, with an in-process cache to avoid redundant API calls.
- `enrich_missing_underlying_prices(user_id)` — idempotent bulk enricher that fills `underlying_at_entry` for all option trades that are missing it; writes into `trade_annotations`, creating the row if needed.

---

## v1.13.1 - 2026-03-14

### Bug Fixes
- Fixed table formatting in the trade notes section.

---

## v1.13.0 - 2026-03-14

### New Features
- **Trade context annotations** — Three new fields on the annotation form: ATM Engaged (not used / entry only / full session), Exit Reason (Hit T1/T2/T3, stopped out, time stop, early exit, held too long), and Underlying Price at Entry (options only — records the spot price of the underlying at fill time for future plan adherence analysis).
- These fields are included in the admin annotation export (format v2.0).

### Improvements
- Notes field on trade detail page now fills the viewport height and scrolls internally, with the Save button always visible below it.

---

## v1.12.3 - 2026-03-13

### Improvements
- Dashboard defaults to "All time" view on load.
- Dashboard account filter dropdown added.
- Account filter now preserved across sort column clicks and pagination links on the trades list.
- Fixed show/hide toggle for dashboard equity curve (replaced `display:none!important` with plain toggle).
- Fixed today's date calculation to use local timezone instead of UTC.

---

## v1.8.0 - 2026-03-12

### New Features
- **Release Notes page** — "About" nav item shows full release history with collapsible accordion; current version expanded by default; markdown rendered to HTML.
- **Admin export** — Export page fetches all active users and merges annotation counts; export download supports multi-user selection with per-user trade grouping and `format_version: "2.0"` payload.

### Improvements
- Admin export now uses `UserManager.list_users()` for consistent user enumeration.

---

## v1.6.0 - 2026-02-28

### New Features
- **Settings page** — Per-user preferences (timezone, display options) stored in the database.
- **API key management** — Users can regenerate their own API key from the Settings page.

### Improvements
- Paginated trades list now persists `per_page` selection across sessions.
- Dashboard date-range filter is preserved in the URL for bookmarking.

---

## v1.5.0 - 2026-02-14

### New Features
- **Admin user management** — Admins can create, deactivate, reactivate, promote, and delete users from `/admin/users`.
- **Batch CSV upload** — Ingest page accepts multiple files in one request.

### Bug Fixes
- Fixed duplicate detection when re-ingesting files with overlapping date ranges.

---

## v1.4.0 - 2026-01-31

### New Features
- **Dashboard analytics** — Comprehensive metrics: win rate, average P&L, largest win/loss, equity curve.
- **Pattern performance report** — Breakdown of P&L and win rate by setup pattern.

### Improvements
- Position tracker now handles partial closes correctly for average cost basis.

---

## v1.3.0 - 2026-01-15

### New Features
- **Trade detail page** — View executions, annotate setup pattern, and add/edit notes for any completed trade.
- **Pattern management** — Managed dropdown for setup patterns via `/admin/patterns`.

---

## v1.2.0 - 2025-12-31

### New Features
- **Multi-user support** — All tables scoped by `user_id`; session-based login with username/password.
- **API key authentication** — SHA-256 hashed keys for programmatic access.
- **Admin mode** — `ADMIN_MODE_ENABLED` env var grants admin access for development/testing.

---

## v1.1.0 - 2025-12-15

### New Features
- **Positions report** — Running totals and average cost basis per symbol.
- **Completed trades report** — Paginated list of round-trip trades with P&L.
- **CLI reporting commands** — `report trades`, `report positions`, `report dashboard`.

---

## v1.0.0 - 2025-12-01

### Initial Release
- NDJSON ingestion from Schwab CSV converter output.
- Three-tier data hierarchy: executions → completed trades → positions.
- Average cost (weighted average) P&L methodology.
- Alembic migrations, SQLAlchemy 2.0, PostgreSQL 14+.
- Click CLI with `ingest`, `db`, `report`, `pattern`, and `notes` command groups.
