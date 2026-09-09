# Plan: Backtest Results Tracker

**Status:** Phase 1 fully delivered, including the follow-up (v1.30.0–v1.38.0, issues
#13–#17, #44, #45). No open items remain from this doc; Phase 2 is an unscheduled
backlog (see bottom). For a full reconciliation of what this plan originally asked for
vs. what actually shipped (including things that shipped without ever being planned,
and things that were asked for but took a follow-up round to land correctly), see
**`docs/backtest-runbook.md`** — treat that file as the accurate "what exists today"
reference; this file is the forward-looking one.

## Context

The user is learning to trade SPX options spreads for income. They'll use external tools (ThinkorSwim OnDemand, TastyTrade Lookback) to manually run backtests of spread strategies (vertical put debit, vertical put credit, iron condors, etc.) across different parameters — entry time of day, spread width, profit target, stop rule, DTE. The goal is to record those results in a structured way so they can compare parameter combinations and find what works.

This is not a simulation engine — it's a structured log of externally-run backtest experiments with analysis/comparison UI.

---

## Phase 1 — Delivered

Everything below shipped. Kept here as a record of what was asked for; where reality
differs from what's described, `backtest-runbook.md` §2–§5 has the specifics.

### Data model (delivered, plus two additions not originally planned)

`backtest_runs`, `backtest_strategy_types`, `backtest_underlyings` as originally
specified below, **plus** an `entry_style` column (`simultaneous` | `staged`) on
`backtest_runs` and a full child table `backtest_leg_rules` (structured per-leg
early-exit rules, e.g. "close long legs when premium ≤ $0.05") — neither was in this
plan when written, both were already in the first migration and are fully wired
through the UI. See runbook §2 for the full column list.

| Column | Type | Notes |
|---|---|---|
| `run_id` | BigInteger PK | |
| `user_id` | BigInteger FK | standard user isolation |
| `strategy_type_id` | FK → `backtest_strategy_types` | managed dropdown |
| `underlying_id` | FK → `backtest_underlyings` | managed dropdown |
| `entry_time` | String(10) | "09:30", "10:00", "12:00" — time-of-day string |
| `spread_width_pts` | Integer | 5, 10, 20, 50 |
| `dte_at_entry` | Integer | 0, 1, 7, 30 |
| `strike_selection` | String(200) | free text: "ATM", "5-delta OTM", "-0.20 delta" |
| `profit_target_pct` | Numeric(5,2) | % of max profit, e.g. 50.00 |
| `stop_loss_rule` | String(200) | free text: "2× debit", "100% loss of premium" |
| `date_range_start` / `date_range_end` | Date | tested period |
| `trade_count`, `win_rate_pct`, `avg_pnl_per_trade`, `total_pnl`, `avg_win`, `avg_loss`, `profit_factor`, `max_win`, `max_loss`, `max_drawdown` | numeric | aggregate results, all nullable |
| `backtest_tool` | String(100) | "ThinkorSwim OnDemand", "TastyTrade Lookback" |
| `notes` | Text | markdown, free-form observations |
| `status` | String(20) | "draft" or "complete" |

### Routes (delivered)

```
/backtest                          list, filterable + sortable
/backtest/new                      GET/POST — create
/backtest/<id>                     GET/POST — detail + edit
/backtest/<id>/delete              POST — delete
/backtest/<id>/leg-rules/add       POST
/backtest/<id>/leg-rules/<rid>/edit    POST
/backtest/<id>/leg-rules/<rid>/delete  POST
```

Inline "add new" strategy type/underlying did **not** ship as separate
`/backtest/strategy-types/add` endpoints as originally planned — it's a `__new__`
sentinel handled inline within the same create/edit POST. Functionally equivalent,
noted here so nobody goes looking for those routes.

### Settings integration (delivered, with the gap this doc now addresses)

`/settings` has Strategy Types and Underlyings management cards: create, inline
rename, deactivate. **Deactivate is hard-blocked whenever any run references the
entry** rather than soft-deactivating, and reactivate was never built. See "Follow-up"
below — this is the one piece of Phase 1 getting revised work.

### Navigation (delivered)

**Backtest** link in the main nav, between Journal and the Tools dropdown.

---

## Follow-up: soft-deactivate + reactivate for strategy types / underlyings — DELIVERED (v1.38.0, issue #45)

**Decision:** build this. Deactivating a strategy type or underlying should succeed
even when backtest runs reference it — it just disappears from the dropdown on *new*
runs — and a Reactivate action should bring it back.

Shipped as specified below, including both fixes called out in "Why this needs more
than removing the block." Verified via `tests/test_backtest_deactivate_reactivate.py`
(5 tests, all passing) plus a full `pytest` run showing no regressions (16 pre-existing
unrelated failures confirmed present on `master` before this change too).

### Why this needs more than removing the block

The current `_load_dropdowns()` in `routes/backtest.py` queries `is_active=True` only,
and that same active-only list is reused for two things beyond populating the "create
new run" dropdown:

1. **`strategy_map`/`underlying_map` on `/backtest` (index route)** — built from the
   active-only list, then used as `strategy_map.get(r.strategy_type_id, '—')` in
   `index.html`. Once a referenced type can be deactivated, any run pointing to it
   would display **"—"** instead of its real strategy/underlying name on the list page.
2. **The `<select>` on `/backtest/<id>` (detail/edit form)** — also built from the
   active-only list. If a run's `strategy_type_id` points to a deactivated type, that
   `<option>` doesn't exist in the dropdown at all, so nothing is pre-selected on page
   load. Saving the edit form without touching that field would submit the browser's
   default (first) option — **silently reassigning the run to a different strategy
   type**. This is a real data-corruption risk, not just a display glitch, and is the
   main reason this is scoped as real work rather than a two-line change.

### Scope

1. **`routes/settings.py`** — `deactivate_bt_strategy` / `deactivate_bt_underlying`:
   remove the `run_count > 0` block; deactivation always succeeds. Keep showing the
   run count in the flash message (informational, not blocking) so the user still
   knows the blast radius.
2. **`routes/settings.py`** — add `reactivate_bt_strategy` / `reactivate_bt_underlying`
   (`POST /settings/backtest-strategy-types/<id>/reactivate`,
   `.../backtest-underlyings/<id>/reactivate`), same shape as deactivate but sets
   `is_active = True`.
3. **`templates/settings/index.html`** — render a Reactivate button when
   `is_active == False` (currently only ever renders Deactivate).
4. **`routes/backtest.py`** — fix the two blast-radius issues above:
   - `index()`: build `strategy_map`/`underlying_map` from *all* types referenced by
     the currently-visible runs (union of active dropdown list + any inactive types
     actually referenced in `runs`), not just the active list.
   - `new()`/`detail()`: when rendering the edit form for an existing run whose
     `strategy_type_id`/`underlying_id` points to an inactive row, include that one
     row in the dropdown options (e.g. appended, visually marked "(inactive)") so it's
     preselected and round-trips correctly if the form is saved untouched.
5. **Filter dropdowns on `/backtest` (list page)** stay active-only — filtering by a
   retired strategy type isn't a real use case, and this matches how the create form's
   dropdown should still behave for *new* runs.

### Verification

- Create a run using strategy type "X". Deactivate "X" from `/settings` — succeeds
  (no block), flash confirms N run(s) affected.
- `/backtest` list still shows "X" (not "—") for that run.
- Open that run's edit page — "X" is selected in the dropdown (marked inactive), not
  blank/defaulted to something else. Save without changing the dropdown — run still
  points to "X" afterward.
- `/backtest/new` — "X" no longer appears in the strategy type dropdown.
- Reactivate "X" from `/settings` — reappears in the `/backtest/new` dropdown.
- `uv run pytest` — no regressions.

### Files touched

| File | Action |
|---|---|
| `trading_journal/web/routes/settings.py` | remove deactivate block; add 2 reactivate routes |
| `trading_journal/web/routes/backtest.py` | fix `strategy_map`/`underlying_map` construction; fix edit-form dropdown to include the run's current (possibly inactive) type |
| `trading_journal/web/templates/settings/index.html` | add Reactivate button per row when inactive |
| `trading_journal/web/templates/backtest/detail.html` | render the run's current type/underlying even if inactive, visually marked |
| `pyproject.toml` | minor version bump (1.37.1 → 1.38.0 — new reactivate capability, not just a fix) |
| `RELEASE_NOTES.md` | new entry |
| `docs/backtest-runbook.md` | §1, §3, §4, §8 updated — points 2 and 3 now marked resolved |
| `tests/test_backtest_deactivate_reactivate.py` | new — 5 tests covering deactivate-while-referenced, list-page name lookup, edit-form preselect, and reactivate round trip for both strategy types and underlyings |

No migration needed — `is_active` already exists on both tables.

---

## Phase 2 — deliberately still unscheduled

No change from the original scope. Confirmed still not started (runbook §6):

- Per-trade detail rows within a run (equity curve, P&L distribution, outlier analysis)
- Chart/visualization of win rate across a parameter grid (heatmap)
- Export of backtest runs in admin export
- Automated import from ThinkorSwim or TastyTrade exports

Decision (2026-09-09): not picking one of these to schedule next. This section stays
a backlog, not a commitment, until there's a reason to pull an item forward.

---

## Reuse / Patterns (still applies to the follow-up work above)

- **Managed dropdown CRUD**: `settings.py` routes for SetupPattern/AtmOption follow
  the same create/edit/deactivate shape being extended here.
- **Flash messages + redirect**: standard pattern throughout.
