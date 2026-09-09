# Backtest Tracker — Runbook (What's Actually Built)

**Status as of:** 2026-09-09 (app v1.38.0)
**Purpose:** `docs/backtestplan.md` is the original design doc for this feature. This
runbook reconciles that plan against the shipped code — what matches, what shipped
differently than planned, what shipped that was never planned, and what from the
original plan is still outstanding. Treat this file as the source of truth for "where
are we," and `backtestplan.md` as a historical design record until it's revised.

---

## 1. Origin and build history

The feature was built as **Phase 1 of a two-phase plan** (`docs/backtestplan.md`):
record externally-run backtest experiments (from ThinkorSwim OnDemand, TastyTrade
Lookback, etc.) as structured rows for comparison — not a simulation engine.

Delivered across six issues, all closed:

| Issue | Title | Shipped in |
|---|---|---|
| #13 | DB schema: migration + SQLAlchemy models | v1.30.0 |
| #14 | List page: `/backtest` with filter, sort, summary | v1.31.0 |
| #15 | Create/edit/delete: `/backtest/new`, `/backtest/<id>` | v1.32.0 |
| #16 | Settings integration: manage strategy types and underlyings | v1.33.0 |
| #17 | Nav wiring, blueprint registration, docs, version bump | v1.33.1 |
| #44 | Fix: backtest pages missing navbar (routes never passed `user=` into templates) | v1.37.1 |
| #45 | Soft-deactivate + reactivate for strategy types/underlyings, plus two dropdown-population bug fixes | v1.38.0 |

`tests/test_backtest_deactivate_reactivate.py` (added in #45) is the only test coverage
for this feature — the core CRUD routes (list/create/edit/delete, leg rules) still have
no dedicated tests, unlike most other project areas of comparable size.

---

## 2. Schema — as built

Four tables, not three. The plan's "New Table" section only specified
`backtest_runs`, `backtest_strategy_types`, `backtest_underlyings` — **`backtest_leg_rules`
and the `entry_style` column were never in `backtestplan.md` or in issue #13's own
body text**, but both were already present when the migration (`2026_06_04_backtest_runs`)
was written, and both are fully wired through the routes and UI. This is the single
biggest plan/reality gap: real capability shipped that the plan doc doesn't mention at all.

### `backtest_runs`
Matches the plan's column list, plus two columns the plan never specified:
- `entry_style VARCHAR(20) NOT NULL DEFAULT 'simultaneous'` — CHECK `IN ('simultaneous', 'staged')`
- (leg rules live in a child table, see below, not a column)

### `backtest_strategy_types` / `backtest_underlyings`
Match the plan exactly — case-insensitive unique per user, `is_active` soft-delete flag,
pre-seeded on first use (Vertical Put Debit/Credit, Iron Condor, Butterfly / SPX, SPY,
QQQ, NDX).

### `backtest_leg_rules` (not in original plan)
Child table for structured per-leg early-exit rules within a run, e.g. "close long legs
when premium ≤ $0.05":

| Column | Notes |
|---|---|
| `rule_id` | PK |
| `run_id` | FK → `backtest_runs`, `ON DELETE CASCADE` |
| `leg_target` | free text, e.g. "long legs", "put spread" |
| `trigger_condition` | free text, e.g. "premium ≤ $0.05" |
| `action` | free text, e.g. "close", "roll" |
| `sort_order` | display order |

This effectively pre-empts part of what the plan called "Phase 2" (more structured
than aggregate-only results) without going as far as full per-trade rows.

---

## 3. Routes — as built vs. planned

| Route | Planned | Built | Notes |
|---|---|---|---|
| `GET /backtest` | ✅ | ✅ | filter (strategy/underlying/entry_time/width), sort on 12 columns, pagination (per-page persisted to session), summary stat cards |
| `GET/POST /backtest/new` | ✅ | ✅ | |
| `GET/POST /backtest/<id>` | ✅ | ✅ | |
| `POST /backtest/<id>/delete` | ✅ | ✅ | modal confirmation (plan just said "confirm dialog") |
| `POST /backtest/strategy-types/add` | ✅ (planned as separate endpoint) | ❌ not built this way | see §4 |
| `POST /backtest/underlyings/add` | ✅ (planned as separate endpoint) | ❌ not built this way | see §4 |
| `POST /backtest/<id>/leg-rules/add` | not planned | ✅ built | |
| `POST /backtest/<id>/leg-rules/<rule_id>/edit` | not planned | ✅ built | |
| `POST /backtest/<id>/leg-rules/<rule_id>/delete` | not planned | ✅ built | |
| Settings CRUD (8 routes, `/settings/backtest-strategy-types/*`, `/settings/backtest-underlyings/*`) | ✅ create/edit/deactivate/**reactivate** | ✅ all four, as of v1.38.0 / issue #45 | see §4 — was missing reactivate, now fixed |

---

## 4. Deviations from the plan worth knowing about

**1. Inline "add new" is a form sentinel, not a separate AJAX endpoint.**
The plan (and issue #15) called for `POST /backtest/strategy-types/add` /
`.../underlyings/add` as standalone routes hit via JS, mirroring the annotate page's
pattern/ATM-option inline-add. What actually shipped: the `<select>` on the create/edit
form gets a `__new__` option; choosing it reveals a text input, and on normal form submit
`_resolve_inline_strategy()` / `_resolve_inline_underlying()` (in `routes/backtest.py`)
create the row inline as part of the same POST — no separate request. Functionally
equivalent from the user's perspective, but it means the "same JS pattern as annotate
form" reuse the plan called for was not actually reused; it's a different (simpler)
mechanism specific to backtest.

**2. ~~Deactivating a strategy type/underlying is hard-blocked if any run references
it~~ — fixed in v1.38.0 (issue #45).**
Issue #16's verification step said: *"Deactivate a strategy type → no longer appears in
dropdown (but existing runs that reference it are unaffected)"*. The original
implementation instead refused to deactivate anything with `run_count > 0`. As of
v1.38.0, deactivate always succeeds; the flash message reports how many runs still
reference it. Fixing this required also fixing the two latent dropdown-population bugs
it would otherwise have exposed: `/backtest`'s `strategy_map`/`underlying_map` now
include any inactive type referenced by a visible run (previously would've shown "—"),
and the `/backtest/<id>` edit form's `<select>` now includes the run's current
type/underlying even when inactive, marked "(inactive)" (previously would have
silently reassigned the run to a different value on save). Covered by
`tests/test_backtest_deactivate_reactivate.py`.

**3. ~~No "reactivate" route or UI~~ — fixed in v1.38.0 (issue #45).**
`reactivate_bt_strategy`/`reactivate_bt_underlying` routes and a Reactivate button
(shown in place of Deactivate for inactive rows) now exist.

**4. Nav placement.** Plan said "between Journal and About." Actual order is
Journal → **Backtest** → Tools (dropdown: Upload/Settings/Admin) → About. Cosmetic
imprecision in the plan text, not a real gap — flagging only for completeness.

---

## 5. UI features that shipped beyond the plan's description

- **Dirty-state tracking** on the detail/edit form — Save is disabled until a field
  actually changes.
- **Delete confirmation modal** (Bootstrap modal, not a browser `confirm()`).
- **Leg Management Rules section** on the detail page: inline add form, per-row
  expand-in-place edit, delete — entirely absent from the original plan (see §2).
- **`entry_style` selector** (Simultaneous / Staged) — absent from the original plan.
- Summary stat cards (best win rate, best profit factor, avg win rate) match plan intent
  but plan only said "summary row."

---

## 6. From the plan, explicitly out of scope — still true today

Nothing in this list has been started. Restating from `backtestplan.md`'s own
"Out of Scope (Phase 2)" section, confirmed still absent from the codebase:

1. **Per-trade detail rows within a run** (equity curve, P&L distribution, outlier
   analysis) — `backtest_runs` remains aggregate-only; there is no child table for
   individual simulated trades (leg rules ≠ trade rows — they're pre-declared exit
   conditions, not results).
2. **Chart/visualization of win rate across a parameter grid** (heatmap) — no charting
   library wired into the backtest pages at all (Chart.js or similar isn't loaded on
   `/backtest`).
3. **Export of backtest runs in admin export** — `/admin/export` (format v3.0) covers
   trade annotations + journal notes only; `BacktestRun` is not part of the exported
   schema.
4. **Automated import from ThinkorSwim / TastyTrade exports** — no parser exists for
   either tool's output; all backtest data entry is manual via the web form.

---

## 7. Quick reference — file map

| File | Role |
|---|---|
| `alembic/versions/2026_06_04_backtest_runs.py` | migration for all 4 tables |
| `trading_journal/models.py` (lines ~725–829) | `BacktestStrategyType`, `BacktestUnderlying`, `BacktestRun`, `BacktestLegRule` |
| `trading_journal/web/routes/backtest.py` | full blueprint — list/create/detail/delete + leg-rule CRUD |
| `trading_journal/web/routes/settings.py` (lines ~444–650) | strategy-type / underlying create/edit/deactivate |
| `trading_journal/web/templates/backtest/index.html` | list + filter + summary |
| `trading_journal/web/templates/backtest/detail.html` | create/edit form, leg rules, delete modal |
| `trading_journal/web/templates/settings/index.html` | strategy type / underlying management cards |
| `docs/backtestplan.md` | original Phase 1 design doc (now stale in places — see above) |

---

## 8. Decisions (2026-09-09) — see `docs/backtestplan.md` for the resulting spec

- **§4.2/§4.3 (hard-block deactivate, no reactivate):** decided to fix this — **built
  and shipped in v1.38.0 (issue #45)**. Soft-deactivate now works even while
  referenced; reactivate routes/UI added; both dropdown-population bugs the change
  would have exposed (`strategy_map`/`underlying_map` on the list page, and the edit
  form's `<select>` silently reassigning a run's type) were fixed alongside it, with
  test coverage in `tests/test_backtest_deactivate_reactivate.py`. Phase 1 is now
  fully closed out — no open items remain from the original plan.
- **Phase 2 priority (per-trade rows / heatmap / export / auto-import):** decided not
  to schedule any of these yet. Remains an unscheduled backlog in `backtestplan.md`.
