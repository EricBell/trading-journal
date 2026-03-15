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
