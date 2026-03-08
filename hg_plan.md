# Plan: Grail Files Integration on Trade Detail Page

## Context

The user maintains a separate `grail_files` PostgreSQL database (same server as trading_journal) populated by the `save-grail-json` project. Each record is a pre-trade JSON plan document created just before a trade is taken. The filename embedded in `file_path` contains a timestamp (e.g., `260303_1009_BATL.json` = 2026-03-03 10:09 ET). Not every completed trade has a matching grail record, but when one exists, the user wants a "View Trade Plan" button on the trade detail page that navigates to a plan display page with a "Back to Trade" button.

## Matching Logic

- Same server as trading_journal; database name = `grail_files`
- Match on: `grail_files.ticker = completed_trades.symbol` AND `file_created_at` date = `opened_at` date (in ET) AND `file_created_at < opened_at`
- When multiple candidates exist: pick the one with the **most recent `file_created_at` before `opened_at`** (LIMIT 1, ORDER BY file_created_at DESC)
- `file_created_at` is timezone-naive in grail_files; `opened_at` is tz-aware in trading_journal — normalize both to ET before comparing

## Implementation Approach

### 1. New module: `trading_journal/grail_connector.py`
- Build a SQLAlchemy engine to the `grail_files` database, reusing same host/port/user/password from the existing `DatabaseConfig` (swap only the `database` attribute)
- Function `find_grail_match(symbol: str, opened_at: datetime) -> dict | None`:
  - Executes raw SQL against grail_files (no ORM model needed — treat as read-only external data)
  - Query: `SELECT * FROM grail_files WHERE ticker = :symbol AND file_created_at::date = :trade_date AND file_created_at < :opened_at_naive ORDER BY file_created_at DESC LIMIT 1`
  - Returns a plain dict (row as mapping) or None if no match
  - Handles connection errors gracefully (log warning, return None) so trade detail still loads if grail DB is unreachable

### 2. Update trade detail route: `trading_journal/web/routes/trades.py`
- In `detail()` (line ~133): after fetching `trade`, call `find_grail_match(trade.symbol, trade.opened_at)` and pass result as `grail_record` to the template
- Add new route `@bp.route('/trades/<int:trade_id>/grail-plan')` with `@login_required`:
  - Re-fetch the trade (same auth check as detail)
  - Re-run `find_grail_match` to get the grail record
  - If no match, flash warning and redirect to trade detail
  - Render `trades/grail_plan.html` with `trade` and `grail_record`

### 3. Update trade detail template: `trading_journal/web/templates/trades/detail.html`
- In the left column card header area (near the trade ID / symbol heading), add conditionally rendered button:
  ```
  {% if grail_record %}
  <a href="{{ url_for('trades.grail_plan', trade_id=trade.completed_trade_id) }}" class="btn btn-sm btn-outline-info">View Trade Plan</a>
  {% endif %}
  ```
- Place it near the top of the detail card so it is immediately visible

### 4. New template: `trading_journal/web/templates/trades/grail_plan.html`
- Extends `base.html`
- Header: symbol + date, with "Back to Trade" button (`url_for('trades.detail', trade_id=trade.completed_trade_id)`)
- Body: placeholder display of key grail fields (ticker, file_created_at, trade_action, trade_confidence_pct, entry_direction, entry_price, should_trade) and the full `json_content` rendered as a `<pre>` block
- Layout to be refined later — this is intentionally minimal per user requirement ("will be decided on later")

## Critical Files

| File | Action |
|------|--------|
| `trading_journal/grail_connector.py` | Create — DB connection + match query |
| `trading_journal/web/routes/trades.py` | Modify — add grail lookup in `detail()`, add `grail_plan()` route |
| `trading_journal/web/templates/trades/detail.html` | Modify — add conditional "View Trade Plan" button |
| `trading_journal/web/templates/trades/grail_plan.html` | Create — grail plan display page |

## Reuse

- Existing `DatabaseConfig` from `trading_journal/config_manager.py` — reuse host/port/user/password, swap database name
- Existing `db_manager` session pattern from routes — same auth/redirect pattern for new route
- Existing Bootstrap 5 button and card styles from `detail.html`

## Verification

1. Navigate to a trade that has a matching grail record (e.g., BATL trade from 2026-03-03) — "View Trade Plan" button should appear
2. Navigate to a trade with no grail match — button should not appear
3. Click "View Trade Plan" — navigates to `/trades/<id>/grail-plan` showing grail data
4. Click "Back to Trade" — returns to trade detail
5. If grail DB is down, trade detail still loads normally (no button shown, no error)
