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
