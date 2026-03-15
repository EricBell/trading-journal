# Notes to build out further


 before you build it, you  mention that data could/should be collected that wasn't. going forward in days to come is there data I should collect?                                                                  
                                                                                                                                                   
● Good instinct to ask this before building — it shapes what's worth building now vs later.                                                                                                                         
                                                                                                                                                                                                                    
  Here's a structured breakdown of the data gap:   
                                                                                                                                                                                                                    
  ---
  The critical missing piece: underlying price at option entry                                                                                                                                                      
                  
  The plan says "wait for SPY to pull back to $687.88." Your broker CSV records the option premium you paid ($0.21). We have no record of what SPY spot was at the moment of your fill.                             
                                                                                                                                                                                                                    
  Without it, entry zone adherence for options is permanently blind. It's the single highest-value data point missing. Options are:
  1. Fetch automatically — Polygon.io, Alpaca, or Schwab's own API can give you 1-minute OHLCV for the underlying. You already have the ohlcv_price_series table stub sitting empty. It was built for this.
  2. Enter manually — A simple field on the annotation form: "Underlying at entry: ___". Tedious but accurate.

  ---
  Data you should start capturing going forward

  Category 1: Post-trade annotation (add to the annotation form — low effort, high value)
+----------------------+---------------------------+
| Field                | Why it matters            |
+----------------------+---------------------------+
| ATM engaged?         | Compare ATM-guided vs     |
| Not used / Entry     | manual trades over time.  |
| only / Full session  | This is your biggest      |
|                      | unknown right now.        |
+----------------------+---------------------------+
| Exit reason          | Distinguishes "I followed |
| Hit T1 / Hit T2 /    | the plan and stopped out" |
| Stopped out / Time   | from "I panicked early."  |
| stop / Early         | Completely different      |
| discretionary /      | learning signal.          |
| Held too long        |                           |
+----------------------+---------------------------+
| Plan overridden?     | When you deviated from    |
| Yes/No + reason      | the plan, was it          |
|                      | intentional and why?      |
+----------------------+---------------------------+
| Underlying at entry  | Manual field for now.     |
| options only         | Lets us check your entry  |
|                      | zone discipline until     |
|                      | market data is wired up.  |
+----------------------+---------------------------+

Category 2: Automatic enrichment
(requires a market data integration
— medium effort)

+----------------------+---------------------------+
| Data                 | Source                    |
+----------------------+---------------------------+
| Underlying OHLCV at  | Polygon.io free tier /   |
| trade time           | Schwab API               |
+----------------------+---------------------------+
| Did price ever reach | Same                      |
| T1/T2?               |                           |
+----------------------+---------------------------+
| VIX at trade time    | Same                      |
+----------------------+---------------------------+

+----------------------+---------------------------+
| Data                 | What it unlocks           |
+----------------------+---------------------------+
| Underlying OHLCV at  | Entry zone pass/fail for  |
| trade time           | options, high-of-day      |
|                      | context                   |
+----------------------+---------------------------+
| Did price ever reach | True counterfactual:      |
| T1/T2?               | "T1 was reachable and you |
|                      | left it on the table" vs  |
|                      | "T1 was never touched"    |
+----------------------+---------------------------+
| VIX at trade time    | Correlate trade           |
|                      | performance with          |
|                      | volatility regime         |
+----------------------+---------------------------+
```


  Category 3: ATM session data (requires new pipeline — future, but worth designing for)

  Right now you have zero visibility into what ATM did during a session. Eventually you'd want:
  - ATM signal log (what it said and when)
  - ATM recommended exits vs what you actually did
  - Whether ATM was overriding the HG plan or following it

  Even a simple text field ("ATM session notes") in the annotation form gives you a place to paste a summary now.

  ---
  My recommendation before we build anything

  Add 3 fields to the annotation form first:
  1. ATM engaged (dropdown: Not used / Entry signal only / Full session)
  2. Exit reason (dropdown: Hit T1 / Hit T2 / Stopped out / Time stop / Early exit / Held too long / Other)
  3. Underlying at entry (number field, optional, shown only for options trades)

  These cost very little to build (one small migration + annotation form update), but they make every future analysis significantly more accurate. Then build the Plan Adherence card on top of that richer data.

  Want me to add those three fields as part of the plan adherence feature, or as a separate first step?

---
Plan: Massive.com API Integration — Underlying Price Auto-Enrichment

Context

Options trades store the premium paid but not what the underlying was trading at when the fill occurred. Without it, entry-zone discipline, such as “wait for SPY to pull back to $687,” cannot be measured. The `underlying_at_entry` field already exists on `trade_annotations`, and the `ohlcv_price_series` table is already stubbed out exactly for this purpose.

This plan wires up Massive.com, formerly Polygon.io, to automatically populate `underlying_at_entry` after each CSV upload, using the 1-minute aggregate bar closest to `opened_at` for every option trade.

---

What the user must provide

One thing only: the Massive.com API key.

Set it as an environment variable named `MASSIVE_API_KEY` in Dokploy’s environment variable panel, the same place `DB_HOST` and similar values are set. The app will silently skip enrichment if the key is absent, so the upload flow is never broken.

The key is located at:

Massive.com account dashboard → API Keys

---

Approach

A new `market_data.py` module follows the same fire-and-forget pattern as `grail_connector.py`. If Massive is unreachable or the key is wrong, a warning is logged and the upload completes normally. No user-facing error is raised.

Enrichment is synchronous on upload, called from the web ingest route immediately after `reprocess_all_completed_trades()` returns. Typical cost is one API call per option trade, usually 2 to 6 per session, adding about 1 to 2 seconds to the upload redirect.

Enrichment is idempotent: only option trades where `underlying_at_entry IS NULL` are fetched. Re-uploading the same file is safe.

---

Massive API call

Endpoint used:

`GET https://api.polygon.io/v2/aggs/ticker/{UNDERLYING}/range/1/minute/{from_ts}/{to_ts}?adjusted=false&sort=asc&limit=5&apiKey={MASSIVE_API_KEY}`

Parameters and behavior:

* `{UNDERLYING}` = `option_details['underlying']`, for example `SPY`
* Time window = `[opened_at - 2 minutes, opened_at + 2 minutes]` to handle off-by-one bar-boundary issues
* Use the close price of the bar whose `t` value, in milliseconds since epoch, is closest to `opened_at`

Response field mapping into `ohlcv_price_series`:

* `t` → `timestamp`
* `o` → `open_price`
* `h` → `high_price`
* `l` → `low_price`
* `c` → `close_price`
* `v` → `volume`
* `timeframe` = `'1m'`

---

Files to create or modify

1. New file: `trading_journal/market_data.py`

Create a `MassiveClient` class.

`__init__`

* Reads `MASSIVE_API_KEY` from the environment
* Sets `self.enabled = bool(key)`

`get_underlying_close_at(symbol: str, ts: datetime) -> Optional[float]`

* Returns `None` immediately if `self.enabled` is false
* Checks the `ohlcv_price_series` cache first using a select by symbol plus timestamp ± 30 seconds plus `timeframe='1m'`
* If cache misses, performs an HTTP GET to the Massive aggregate endpoint
* On HTTP 200, inserts returned bars into `ohlcv_price_series` using `INSERT ... ON CONFLICT DO NOTHING`
* Returns the close price of the bar closest to `ts`
* On any exception, logs a warning and returns `None`

Also create a standalone function:

`enrich_missing_underlying_prices(user_id: int) -> dict`

Behavior:

* Standalone rather than a class method so it can be called easily from routes
* Queries `CompletedTrade` joined with a left outer join to `TradeAnnotation`
* Filters:

  * `user_id = user_id`
  * `instrument_type = 'OPTION'`
  * annotation missing or `underlying_at_entry IS NULL`
* For each result:

  * Extracts the underlying from `option_details['underlying']`
  * Calls `client.get_underlying_close_at(underlying, trade.opened_at)`
  * If a value is returned, gets or creates a `TradeAnnotation`, sets `underlying_at_entry`, and commits
* Returns a summary dictionary such as:

  * `{'enriched': N, 'skipped': M, 'failed': K}`

The `_get_or_create_annotation` logic already exists in `trading_journal/web/routes/trades.py:16–29`. Replicate that same simple pattern here rather than importing route-layer code into the core module.

2. Modify `trading_journal/web/routes/ingest.py`

After the existing call to:

`engine.reprocess_all_completed_trades(user_id)`

Add:

```python
from ...market_data import enrich_missing_underlying_prices

enrichment = enrich_missing_underlying_prices(user_id)
```

Include enrichment counts in the flash message if any were enriched, for example:

“3 underlying prices filled in automatically.”

3. New Alembic migration: `alembic/versions/2026_03_15_ohlcv_unique_constraint.py`

The `ohlcv_price_series` table has no unique constraint in the Python model even though `OVERVIEW.md` says `(symbol, timestamp, timeframe)` should be unique.

Add a migration to create that constraint so `INSERT ... ON CONFLICT DO NOTHING` works correctly:

```python
op.create_unique_constraint(
    'uq_ohlcv_symbol_ts_tf',
    'ohlcv_price_series',
    ['symbol', 'timestamp', 'timeframe']
)
```

Use `sa.inspect` to check for existence first, following the idempotent migration pattern already used elsewhere in the codebase.

4. Modify `pyproject.toml`

Bump the minor version for the new feature:

`1.13.0 → 1.14.0`

No changes are needed to `config_manager.py`. Reading `os.environ.get('MASSIVE_API_KEY')` directly in `market_data.py` is consistent with how other env-only secrets are handled.

---

Key existing code to reuse

Fire-and-forget external DB pattern
Location: `trading_journal/grail_connector.py:62–64`

`_get_or_create_annotation` logic
Location: `trading_journal/web/routes/trades.py:16–29`

Idempotent migration pattern using `sa.inspect`
Location: `alembic/versions/2026_03_09e_trade_annotations_table.py:22–28`

Ingest route call site
Location: `trading_journal/web/routes/ingest.py` after `reprocess_all_completed_trades`

`option_details['underlying']` field source
Location: `trade_completion.py:243` via `option_details=first_open.option_data`

---

Verification

1. Unit smoke test

Set `MASSIVE_API_KEY` to an invalid key and upload a CSV with option trades. Confirm:

* The upload succeeds
* A warning is logged
* `underlying_at_entry` remains `NULL`

2. Happy path

Set a valid `MASSIVE_API_KEY` and upload a CSV with option trades. Confirm:

* `underlying_at_entry` is populated on the trade detail annotation panel
* `ohlcv_price_series` receives rows for the fetched bars
* Re-uploading the same file produces no additional API calls because of cache hits
* `underlying_at_entry` remains unchanged on re-upload

3. Optional CLI backfill

If desired, expose `enrich_missing_underlying_prices` as a CLI command such as:

`trading-journal market-data enrich`

This would allow historical trades to be backfilled later without changing the core implementation plan.

---

