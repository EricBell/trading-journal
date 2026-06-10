# Plan: Backtest Results Tracker

## Context

The user is learning to trade SPX options spreads for income. They'll use external tools (ThinkorSwim OnDemand, TastyTrade Lookback) to manually run backtests of spread strategies (vertical put debit, vertical put credit, iron condors, etc.) across different parameters — entry time of day, spread width, profit target, stop rule, DTE. The goal is to record those results in a structured way so they can compare parameter combinations and find what works.

This is not a simulation engine — it's a structured log of externally-run backtest experiments with analysis/comparison UI.

---

## Data Model

### Two-phase approach

**Phase 1 (this work): Aggregate results per run** — one row per parameter combination tested. Low data-entry burden, enables comparison across strategies and parameters.

**Phase 2 (future): Per-trade detail** — individual trade rows within a run. Enables equity curve, P&L distribution, outlier analysis. More data entry, more power.

---

### New table: `backtest_runs`

| Column | Type | Notes |
|---|---|---|
| `run_id` | BigInteger PK | |
| `user_id` | BigInteger FK | standard user isolation |
| `strategy_type` | String(50) | "vertical_put_debit", "vertical_put_credit", "iron_condor", "butterfly" — managed dropdown |
| `underlying` | String(20) | "SPX", "SPY", "QQQ" — managed dropdown |
| `entry_time` | String(10) | "09:30", "10:00", "12:00" — time-of-day string |
| `spread_width_pts` | Integer | 5, 10, 20, 50 |
| `dte_at_entry` | Integer | 0, 1, 7, 30 |
| `strike_selection` | String(200) | free text: "ATM", "5-delta OTM", "-0.20 delta" |
| `profit_target_pct` | Numeric(5,2) | % of max profit, e.g. 50.00 |
| `stop_loss_rule` | String(200) | free text: "2× debit", "100% loss of premium" |
| `date_range_start` | Date | first date in tested period |
| `date_range_end` | Date | last date in tested period |
| `trade_count` | Integer | number of trades in the backtest |
| `win_rate_pct` | Numeric(5,2) | |
| `avg_pnl_per_trade` | Numeric(12,2) | |
| `total_pnl` | Numeric(12,2) | |
| `avg_win` | Numeric(12,2) | |
| `avg_loss` | Numeric(12,2) | |
| `profit_factor` | Numeric(8,4) | total_win ÷ \|total_loss\| |
| `max_win` | Numeric(12,2) | |
| `max_loss` | Numeric(12,2) | |
| `max_drawdown` | Numeric(12,2) | |
| `backtest_tool` | String(100) | "ThinkorSwim OnDemand", "TastyTrade Lookback" |
| `notes` | Text | markdown, free-form observations |
| `status` | String(20) | "draft" or "complete" |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### New managed-dropdown table: `backtest_strategy_types`

Follows exact pattern of `setup_patterns` / `atm_options`: `(strategy_type_id, user_id, strategy_name, is_active, created_at, updated_at)` with case-insensitive unique per user.

Pre-seeded on first use with: Vertical Put Debit, Vertical Put Credit, Iron Condor, Butterfly.

### New managed-dropdown table: `backtest_underlyings`

Same pattern: `(underlying_id, user_id, underlying_name, is_active, ...)`. Pre-seeded: SPX, SPY, QQQ, NDX.

---

## New Routes

```
/backtest                    GET   — list all runs, filterable + sortable
/backtest/new                GET   — create form
/backtest/new                POST  — save new run
/backtest/<id>               GET   — detail + edit
/backtest/<id>               POST  — update run
/backtest/<id>/delete        POST  — delete run
```

### List page (`/backtest`)
- Filter bar: strategy_type, underlying, entry_time, spread_width_pts
- Sortable columns: win_rate_pct, profit_factor, avg_pnl_per_trade, total_pnl, trade_count, date
- Summary row at top: across all visible runs — best win rate, best profit factor, avg win rate
- Status badge (draft/complete)
- "New Run" button

### Detail/Edit page (`/backtest/<id>`)
- Two-section layout: **Parameters** (top) | **Results** (bottom)
- All fields editable inline (single form, POST to save)
- Notes field uses EasyMDE markdown editor (same as journal)
- Delete button with confirm

### Create form (`/backtest/new`)
- Same two-section layout as detail
- Strategy type and underlying are managed dropdowns (with inline "add new" like patterns on annotate form)
- Result fields optional on create (can be filled in later)

---

## Settings Integration

Add a **Backtest** tab (or card) to `/settings` for managing:
- Strategy types (create, rename, deactivate)
- Underlyings (create, rename, deactivate)

Follows exact pattern of existing SetupPattern / AtmOption management cards.

---

## Navigation

Add **Backtest** link to the main sidebar nav, between Journal and About.

---

## Files to Create / Modify

| File | Action |
|---|---|
| `alembic/versions/2026_06_XX_backtest_runs.py` | New migration: backtest_runs, backtest_strategy_types, backtest_underlyings tables |
| `trading_journal/models.py` | Add BacktestRun, BacktestStrategyType, BacktestUnderlying models + User relationships |
| `trading_journal/web/routes/backtest.py` | New blueprint: list, create, detail, update, delete |
| `trading_journal/web/templates/backtest/index.html` | List + filter view |
| `trading_journal/web/templates/backtest/detail.html` | Create/edit form |
| `trading_journal/web/routes/settings.py` | Add strategy type + underlying CRUD routes |
| `trading_journal/web/templates/settings/index.html` | Add two new management cards |
| `trading_journal/web/__init__.py` | Register backtest blueprint |
| `trading_journal/web/templates/base.html` (or nav partial) | Add Backtest nav link |
| `pyproject.toml` | Version bump (minor — new feature) |
| `RELEASE_NOTES.md` | New entry |
| `docs/OVERVIEW.md` | Update schema table, route table, file map |

---

## Reuse / Patterns

- **Managed dropdown CRUD**: copy pattern from `settings.py` routes for SetupPattern/AtmOption — identical create/edit/deactivate logic
- **Markdown editor**: copy EasyMDE setup from `journal/detail.html`
- **Sort/filter/pagination**: copy `?sort=&dir=&page=` pattern from `trades.py` / `positions.py`
- **Flash messages + redirect**: standard pattern throughout

---

## Verification

1. `uv run alembic upgrade head` — migration applies cleanly
2. Navigate to `/backtest/new`, create a run with all fields populated, save → appears in list
3. Edit a run, change win rate, save → list reflects updated value
4. Filter list by strategy type → only matching rows shown
5. Sort by profit_factor descending → highest profit factor at top
6. `/settings` → Backtest cards show strategy types + underlyings, inline add/deactivate works
7. Delete a run → removed from list
8. `uv run pytest` — no regressions

---

## Out of Scope (Phase 2)

- Per-trade detail rows within a run (equity curve, P&L distribution)
- Chart/visualization of win rate across parameter grid (heatmap)
- Export of backtest runs in admin export
- Automated import from ThinkorSwim or TastyTrade exports
