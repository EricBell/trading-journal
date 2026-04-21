# HG Historical Market Data & Evaluation Design

## Purpose

This document defines the database design for adding historical market data hydration and stored HG evaluation to the trading journal app.

The scope here is intentionally limited to:

- on-demand fetching of historical market data for a selected HG plan
- storing retrieved raw bars in the existing shared OHLCV cache
- storing an audit trail of HG-specific fetch requests
- storing deterministic evaluation results for each HG against the fetched data

This document does **not** define service interfaces or application code structure. Those can be implemented separately.

---

## Architectural Intent

HG plans are external to the core trade-ingest flow and already exist as durable records outside the app. The app already has market-data support and an OHLCV cache table. The cleanest design is to treat HG analysis as a separate derived layer built on top of shared raw bars.

The design separates three concerns:

1. **Raw bar storage**
   - shared market-data cache
   - one canonical copy of each bar per symbol/timestamp/timeframe

2. **HG market-data request tracking**
   - which HG requested which window
   - whether the fetch succeeded
   - how many bars were expected and received

3. **HG evaluation results**
   - whether the HG entry was touched
   - how the entry zone was touched
   - whether TP1 and TP2 were reached
   - excursion and timing metrics
   - a versioned analysis output that can be recomputed later

This separation is important because bars are reusable, while HG evaluation logic will likely evolve.

---

## Existing Table Usage

The existing `ohlcv_price_series` table remains the canonical raw-bar store.

It should continue to behave as a shared cache keyed by:

- `symbol`
- `timestamp`
- `timeframe`

No HG-specific foreign key should be added to this table in v1.

Reason:

- a given 1-minute bar for a symbol should exist only once
- multiple HGs may refer to the same bar range
- linking bars directly to HG requests would break cache semantics and encourage duplication

---

## Data Window Rules

### Initial fetch rule

For a selected HG plan, fetch bars for:

- 30 minutes before HG plan creation time
- 90 minutes after HG plan creation time

### Linked trade extension rule

If a recorded trade is linked to the HG and the linked trade exits later than `HG creation time + 90 minutes`, extend the fetch window to:

- 30 minutes before HG creation time
- linked trade exit time

### Design note

The fetch window and the evaluation window should be treated as separate concepts.

- **Fetch window**: broader window to avoid missing useful context
- **Evaluation window**: window used for deterministic outcome analysis

This allows later refinement without requiring a bar refetch.

### Recommended practical default

For phase 1, the design can support:

- fetch window: `t - 30 minutes` through `t + 90 minutes`
- optional extension to linked trade exit time when appropriate

Evaluation can initially use the same window for simplicity, but the schema should not require that forever.

---

## Evaluation Semantics

This first version is based on **underlying price bars**, not option contract pricing.

That means:

- equity HGs are evaluated directly against the equity bars
- option HGs are still evaluated against the underlying bars when the HG is fundamentally an underlying-price plan
- actual option-trade performance remains a separate concern from HG-plan validity

### Entry touched

If the HG entry is a zone `[entry_zone_low, entry_zone_high]`, entry is considered touched when price overlaps the zone.

For a long setup, a bar overlaps the zone if:

- `low <= entry_zone_high`
- `high >= entry_zone_low`

For a short setup, the same overlap concept applies, but the later interpretation of touch direction is mirrored.

### Entry touch classification

The first pass should classify the first meaningful touch as one of:

- `never`
- `top_of_zone`
- `in_zone`
- `bottom_of_zone`
- `through_zone`

Interpretation:

- `never`: entry zone was not touched during the evaluation window
- `top_of_zone`: first touch was only at the near edge of the zone
- `in_zone`: touch entered the interior of the zone without reaching the far edge
- `bottom_of_zone`: touch reached the far edge of the zone
- `through_zone`: price moved through the zone past the far edge

For short setups, these labels are mirrored semantically even if the stored values remain the same.

### TP1 / TP2 reached

Targets should only be evaluated **after entry is first touched**.

For long setups:

- TP1 reached if any post-entry bar `high >= target_1_price`
- TP2 reached if any post-entry bar `high >= target_2_price`

For short setups:

- TP1 reached if any post-entry bar `low <= target_1_price`
- TP2 reached if any post-entry bar `low <= target_2_price`

### Important limitation

This is **bar-based analysis**, not execution truth.

A 1-minute bar can show both entry and target touched without proving precise intrabar sequencing. Results should therefore be interpreted as:

- bar-based entry touch
- bar-based target reach

This is acceptable for v1 and appropriate for comparative HG analysis.

---

## Recommended New Tables

Two new tables should be added:

1. `hg_market_data_requests`
2. `hg_analysis_results`

---

# Table 1: `hg_market_data_requests`

## Purpose

Stores the audit trail and status of historical market-data fetches requested for a specific HG plan.

This table answers:

- which HG requested data
- for what symbol and timeframe
- for what time window
- why that window was chosen
- whether the fetch succeeded
- whether the returned data appears complete

## SQL

```sql
CREATE TABLE hg_market_data_requests (
    hg_market_data_request_id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,

    -- external grail plan identity
    grail_plan_id TEXT NOT NULL,
    grail_plan_created_at TIMESTAMPTZ NOT NULL,

    -- optional local link to a trade already matched to this plan
    completed_trade_id BIGINT NULL
        REFERENCES completed_trades(id) ON DELETE SET NULL,

    -- market data request identity
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,              -- '1m', later maybe '5m', '15m'
    fetch_start_at TIMESTAMPTZ NOT NULL,
    fetch_end_at   TIMESTAMPTZ NOT NULL,

    -- why this window was chosen
    request_source TEXT NOT NULL DEFAULT 'manual',   -- manual | batch | trade_linked
    window_rule TEXT NOT NULL,                       -- e.g. 't-30_to_t+90', 'extended_to_trade_exit'
    linked_trade_exit_at TIMESTAMPTZ NULL,

    -- fetch result bookkeeping
    status TEXT NOT NULL DEFAULT 'pending',          -- pending | success | partial | failed
    bars_expected INTEGER NULL,
    bars_received INTEGER NULL,
    first_bar_at TIMESTAMPTZ NULL,
    last_bar_at  TIMESTAMPTZ NULL,

    provider TEXT NOT NULL DEFAULT 'massive',
    provider_request_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_text TEXT NULL,

    fetched_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_hg_market_data_requests_timeframe
        CHECK (timeframe IN ('1m', '5m', '15m', '1d')),

    CONSTRAINT chk_hg_market_data_requests_status
        CHECK (status IN ('pending', 'success', 'partial', 'failed')),

    CONSTRAINT chk_hg_market_data_requests_source
        CHECK (request_source IN ('manual', 'batch', 'trade_linked')),

    CONSTRAINT chk_hg_market_data_requests_window
        CHECK (fetch_end_at > fetch_start_at),

    CONSTRAINT uq_hg_market_data_request_window
        UNIQUE (user_id, grail_plan_id, timeframe, fetch_start_at, fetch_end_at)
);

CREATE INDEX ix_hg_market_data_requests_user_created
    ON hg_market_data_requests (user_id, created_at DESC);

CREATE INDEX ix_hg_market_data_requests_plan
    ON hg_market_data_requests (user_id, grail_plan_id);

CREATE INDEX ix_hg_market_data_requests_trade
    ON hg_market_data_requests (completed_trade_id);

CREATE INDEX ix_hg_market_data_requests_symbol_time
    ON hg_market_data_requests (symbol, timeframe, fetch_start_at, fetch_end_at);
```

## Column Notes

### `grail_plan_id`
The durable external HG identifier. This should point to the authoritative HG record in the grail system.

### `grail_plan_created_at`
The canonical HG timestamp used for window construction. This should represent the actual plan creation time, not a later update time and not a UI view time.

### `completed_trade_id`
Optional link to the trade already associated with this HG. This allows extension of fetch windows and later trade-vs-HG comparison.

### `window_rule`
Stores the logic used to determine the fetch window. This is useful for debugging and for future migrations in logic.

Suggested values:

- `t-30_to_t+90`
- `extended_to_trade_exit`

### `provider_request_meta`
JSONB field for storing provider-side metadata or request parameters that may help debugging. This should not be used as a substitute for first-class columns.

### `status`
Represents fetch lifecycle state:

- `pending`
- `success`
- `partial`
- `failed`

`partial` is useful when some bars were returned but the returned range is incomplete.

## Design Rationale

This table should exist even though bars are stored in a shared cache.

Without this table, the app cannot reliably answer:

- whether a given HG has already been hydrated
- whether the stored bar coverage is complete for the requested HG window
- what exact request was made
- whether a failed fetch should be retried

This table is also the natural anchor for future batch backfill jobs.

---

# Table 2: `hg_analysis_results`

## Purpose

Stores deterministic, versioned HG evaluation results produced from a specific HG market-data request.

This table answers:

- was the entry zone touched
- how was it touched
- were TP1 and TP2 reached
- how many bars elapsed before outcomes
- what were the favorable and adverse excursions
- what evaluator version produced the result

## SQL

```sql
CREATE TABLE hg_analysis_results (
    hg_analysis_result_id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,

    hg_market_data_request_id BIGINT NOT NULL
        REFERENCES hg_market_data_requests(hg_market_data_request_id) ON DELETE CASCADE,

    -- denormalized external identity for easy querying
    grail_plan_id TEXT NOT NULL,
    grail_plan_created_at TIMESTAMPTZ NOT NULL,

    completed_trade_id BIGINT NULL
        REFERENCES completed_trades(id) ON DELETE SET NULL,

    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,

    analysis_version INTEGER NOT NULL DEFAULT 1,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- plan parameters captured at evaluation time so results remain stable
    side TEXT NOT NULL,                          -- long | short
    instrument_type TEXT NOT NULL,              -- equity | option
    entry_zone_low NUMERIC(18,8) NOT NULL,
    entry_zone_high NUMERIC(18,8) NOT NULL,
    target_1_price NUMERIC(18,8) NULL,
    target_2_price NUMERIC(18,8) NULL,
    stop_price NUMERIC(18,8) NULL,

    -- window actually evaluated
    eval_start_at TIMESTAMPTZ NOT NULL,
    eval_end_at   TIMESTAMPTZ NOT NULL,

    bars_scanned INTEGER NOT NULL DEFAULT 0,

    -- entry behavior
    entry_touched BOOLEAN NOT NULL DEFAULT FALSE,
    entry_first_touch_at TIMESTAMPTZ NULL,
    entry_touch_type TEXT NOT NULL DEFAULT 'never',
    entry_touch_price NUMERIC(18,8) NULL,

    -- target behavior (only meaningful after entry touch)
    tp1_reached BOOLEAN NOT NULL DEFAULT FALSE,
    tp1_reached_at TIMESTAMPTZ NULL,
    tp2_reached BOOLEAN NOT NULL DEFAULT FALSE,
    tp2_reached_at TIMESTAMPTZ NULL,

    -- useful path metrics
    max_favorable_excursion NUMERIC(18,8) NULL,
    max_adverse_excursion NUMERIC(18,8) NULL,
    mfe_at TIMESTAMPTZ NULL,
    mae_at TIMESTAMPTZ NULL,

    bars_to_entry INTEGER NULL,
    bars_from_entry_to_tp1 INTEGER NULL,
    bars_from_entry_to_tp2 INTEGER NULL,

    -- optional trade comparison hooks for later UI
    linked_trade_opened_at TIMESTAMPTZ NULL,
    linked_trade_closed_at TIMESTAMPTZ NULL,
    linked_trade_entry_price NUMERIC(18,8) NULL,
    linked_trade_exit_price NUMERIC(18,8) NULL,

    notes JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_hg_analysis_results_timeframe
        CHECK (timeframe IN ('1m', '5m', '15m', '1d')),

    CONSTRAINT chk_hg_analysis_results_side
        CHECK (side IN ('long', 'short')),

    CONSTRAINT chk_hg_analysis_results_instrument_type
        CHECK (instrument_type IN ('equity', 'option')),

    CONSTRAINT chk_hg_analysis_results_touch_type
        CHECK (entry_touch_type IN (
            'never',
            'top_of_zone',
            'in_zone',
            'bottom_of_zone',
            'through_zone'
        )),

    CONSTRAINT chk_hg_analysis_results_eval_window
        CHECK (eval_end_at > eval_start_at),

    CONSTRAINT chk_hg_analysis_results_entry_zone
        CHECK (entry_zone_high >= entry_zone_low),

    CONSTRAINT uq_hg_analysis_results_version
        UNIQUE (hg_market_data_request_id, analysis_version)
);

CREATE INDEX ix_hg_analysis_results_user_plan
    ON hg_analysis_results (user_id, grail_plan_id);

CREATE INDEX ix_hg_analysis_results_trade
    ON hg_analysis_results (completed_trade_id);

CREATE INDEX ix_hg_analysis_results_symbol_eval
    ON hg_analysis_results (symbol, eval_start_at, eval_end_at);

CREATE INDEX ix_hg_analysis_results_outcomes
    ON hg_analysis_results (user_id, entry_touched, tp1_reached, tp2_reached);
```

## Column Notes

### `analysis_version`
Critical field. Evaluation logic will evolve. This allows you to recompute results later without losing interpretability of historical rows.

### `side`
Allowed values:

- `long`
- `short`

This should describe the HG setup direction, not necessarily the eventual instrument execution method.

### `instrument_type`
Allowed values:

- `equity`
- `option`

This captures the plan's trading instrument context while still allowing the plan to be evaluated against underlying bars.

### `entry_zone_low` / `entry_zone_high`
These should be copied into the result row at evaluation time.

Reason:

the result should snapshot the exact numeric interpretation used by the evaluator, even if HG parsing logic changes later.

### `entry_touch_price`
Optional field storing a representative touch price at first entry overlap. It may be useful for debugging or UI summaries, but it should not be treated as execution truth.

### `tp1_reached` / `tp2_reached`
Targets should only be considered reached after entry has first been touched.

### `max_favorable_excursion` / `max_adverse_excursion`
These are highly valuable analytical metrics and should be included in v1.

They help answer:

- whether HGs are directionally correct even when targets are missed
- whether entries are too early
- whether targets are too conservative or too ambitious

### `notes`
JSONB scratch space for supplemental analysis metadata or future additions that do not yet deserve schema columns.

Use sparingly.

## Design Rationale

The result table should not be computed live on every page render.

Reasons:

- evaluation logic should be deterministic and cacheable
- later analytics and filtering need queryable stored fields
- results should be versioned and reproducible

The result row should store both the fetch anchor (`hg_market_data_request_id`) and denormalized HG identity (`grail_plan_id`) so that querying is easy and historical interpretation remains durable.

---

## Existing Table: `ohlcv_price_series`

## Recommendation

Keep `ohlcv_price_series` structurally unchanged for v1.

It remains the shared bar cache.

Do **not** add:

- `hg_market_data_request_id`
- `grail_plan_id`

to this table.

## Optional small extension

If provenance on cached bars would be useful, the following small extension is acceptable:

```sql
ALTER TABLE ohlcv_price_series
    ADD COLUMN provider TEXT NULL,
    ADD COLUMN fetched_at TIMESTAMPTZ NULL;
```

This is optional.

It should only be added if the existing table does not already capture equivalent information.

---

## Key Identity Model

The design should follow this model:

### `ohlcv_price_series`
One canonical raw bar per:

- symbol
- timestamp
- timeframe

### `hg_market_data_requests`
One request record per HG fetch window and timeframe.

Represents:

- "I asked for this market data for this HG."

### `hg_analysis_results`
One evaluation record per request and analysis version.

Represents:

- "Using this HG request and this evaluator version, here is the computed outcome."

This gives a clean, layered data model.

---

## Timestamp and Numeric Guidance

### Timestamps

Use `TIMESTAMPTZ` consistently across all new HG tables.

This is important because HG linking, trade linking, and window calculations are all timestamp-sensitive.

### Numeric precision

Use `NUMERIC(18,8)` for prices.

This is sufficient for:

- equities
- options
- analytical computations

and avoids floating-point ambiguity in stored result rows.

### Enum strategy

Prefer `TEXT` plus `CHECK` constraints rather than PostgreSQL enum types, unless the project already uses native enums heavily.

Reasons:

- easier migration evolution
- simpler Alembic changes
- lower friction for future additions

---

## What Not to Add Yet

The following should **not** be added in v1:

- direct per-bar linkage from `ohlcv_price_series` to HG requests
- a local duplicate of the full HG JSON in the main app database
- separate result tables for entry logic and target logic
- option-contract-specific historical analytics tables
- live recomputation of HG outcomes on every UI render

These can be revisited later if the product needs them.

---

## Practical Rollout Order

### Phase 1
Add the two new tables:

- `hg_market_data_requests`
- `hg_analysis_results`

Reuse existing `ohlcv_price_series` as the raw cache.

### Phase 2
Implement on-demand HG hydration for a selected HG:

- compute fetch window
- fetch bars from Massive
- upsert bars into `ohlcv_price_series`
- record request status in `hg_market_data_requests`

### Phase 3
Run deterministic evaluator and store results in `hg_analysis_results`.

### Phase 4
Add linked-trade comparison UI and later batch backfill if desired.

---

## Final Recommendation

Ship the following schema for v1:

- `hg_market_data_requests`
- `hg_analysis_results`

Keep `ohlcv_price_series` as the shared raw-bar table.

Optionally add:

- `provider`
- `fetched_at`

to `ohlcv_price_series` if provenance is needed.

This gives a durable and extensible foundation for HG historical analysis while preserving the integrity of the existing bar-cache design.
