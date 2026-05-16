
● Here's a clear breakdown of what's been built:

  ---
  HG Plan Analysis — What's Implemented
  
  "HG" = Historical Grail. The concept: you recorded a pre-trade plan in the grail_files
  database before taking a trade. After the fact, the system fetches 1-minute bars and
  runs the plan through a deterministic bar scan to evaluate whether the setup actually
  played out as planned — regardless of whether you took the trade or not.

  There are actually two separate pipelines that evolved over time, with different
  purposes:

  ---
  Pipeline 1: Trade-Linked HG Analysis

  Files: hg_hydration.py + hg_evaluator.py
  Tables: hg_market_data_requests, hg_analysis_results
  Entry point: Trade detail page "Analyze HG Plan" button, or Admin → HG Analysis batch

  How it works:
  1. Hydration (hydrate_hg_plan): looks up the grail plan, computes a fetch window of
  plan_created_at −30m to +90m (extended to the actual trade exit if the trade ran 
  longer), fetches 1m bars from Polygon.io via MassiveClient, upserts into
  ohlcv_price_series, writes an HgMarketDataRequest row.
  2. Evaluation (evaluate_hg_plan): reads those bars, loads plan parameters (side, entry
  zone, stop, TP1, TP2), runs a chronological bar scan.

  Bar scan produces:
  - Entry touch type: how deeply price entered the entry zone — never, top_of_zone,
  in_zone, bottom_of_zone, through_zone
  - TP1/TP2 reached: single price-point checks (not zone checks)
  - MFE/MAE: max favorable and adverse excursion from the entry touch price
  - Bars-to-entry, bars-to-TP1/TP2
  - Linked trade comparison: actual entry/exit prices vs the plan zone

  The result is stored versioned in hg_analysis_results — keyed by (request_id, 
  analysis_version) so the algorithm can evolve without destroying prior rows.

  ---
  Pipeline 2: Plan-Centric (Grail Plan Browser)

  longer), fetches 1m bars from Polygon.io via MassiveClient, upserts into
  ohlcv_price_series, writes an HgMarketDataRequest row.
  2. Evaluation (evaluate_hg_plan): reads those bars, loads plan parameters (side, entry
  zone, stop, TP1, TP2), runs a chronological bar scan.

  Bar scan produces:
  - Entry touch type: how deeply price entered the entry zone — never, top_of_zone,
  in_zone, bottom_of_zone, through_zone
  - TP1/TP2 reached: single price-point checks (not zone checks)
  - MFE/MAE: max favorable and adverse excursion from the entry touch price
  - Bars-to-entry, bars-to-TP1/TP2
  - Linked trade comparison: actual entry/exit prices vs the plan zone

  The result is stored versioned in hg_analysis_results — keyed by (request_id,
  analysis_version) so the algorithm can evolve without destroying prior rows.

  ---
  Pipeline 2: Plan-Centric (Grail Plan Browser)

  File: grail_analyzer.py
  Table: grail_plan_analyses
  Entry point: Admin → Grail Plan Browser (per-plan "Analyze" button, or "Analyze Next N"
   batch via SSE)

  How it works: Same bar fetch logic, but not tied to any specific trade. Starts from a
  grail_plan_id directly. The fetch window is wider: plan_created_at −90m to +120m.

  Bar scan is zone-based (not point-based): entry zone, stop zone, and TP1 zone all have
  low/high bounds. Phase 1 scans all bars for an entry zone overlap. Phase 2 scans
  subsequent bars — stop has priority: if the same bar touches both stop and TP1, it's a
  failure.

  Outcomes: success, failure, inconclusive, no_entry, no_data, invalid

  no_data results are always retried on subsequent batch runs. The batch uses a
  client-side SSE countdown to avoid nginx proxy timeouts (processes 5 plans, returns,
  client waits 60s, POSTs again).

  ---
  Shared Infrastructure

  Both pipelines share:
  - MassiveClient (market_data.py) — Polygon.io bar fetching; futures use a dedicated
  Massive endpoint that returns no_subscription in the JSON body (HTTP 200) when not
  covered
  - ohlcv_price_series — local bar cache; all fetches upsert here to avoid redundant API
  calls
  - grail_files external DB — read-only source of plan parameters (entry_low/high,
  stop_low/high, tp1_low/high, entry_direction pre-extracted as columns; option plans
  still fall back to JSON for stop/TP since the columns hold option premium, not
  underlying prices)
  - Both are fully idempotent

  ---
  The Gap Between the Two
  
  The trade-linked pipeline (Pipeline 1) uses price-point TPs and produces touch 
  classification + MFE/MAE. The plan-centric pipeline (Pipeline 2) uses zone-based TPs 
  and stop and produces success/failure/inconclusive outcomes. They answer related but
  different questions — Pipeline 1 is "how did price interact with my entry zone on this
  specific trade?" and Pipeline 2 is "would this plan have worked even if I hadn't taken
  the trade?"

✻ Cogitated for 52s

❯ I'm focusing on pipeline 2. The mechanical way to work with it is menu tools | admin | 
   Grail plans. then analyze N number of plans. acknowledge.                             
  
● Acknowledged. Pipeline 2 (grail_analyzer.py → grail_plan_analyses) is the focus. Entry
  point is Admin → Grail Plans, where you can analyze individual plans or batch-analyze N
   at a time via the SSE-based "Analyze Next N" flow.

  What are you looking to do with it?

✻ Churned for 4s

❯ First I want too process a number of plans ingesting them into the system/database     
  then 2nd I want to analyze them. To know what the stats are - how many time when the   
  entry zone was touched did the plan's tp1 get hit vs the plan's stop. things of this   
  nature. I'm trying to figure out how to use the date from the plan to execute them     
  with confidence that I don't currently have.                                           
  
● Let me check what the current Grail Plan Browser already surfaces in terms of stats, so
   I know the gap.
     
  Searched for 2 patterns, read 1 file (ctrl+o to expand)

● Here's the current state and the gap:

  What already works (step 1 — processing):
  The "Analyze Next N" batch on Admin → Grail Plans already does exactly what you
  described — fetches 1m bars from Polygon.io and runs the zone scan for N unanalyzed
  plans. You repeat it until you've processed as many as you want. Results land in
  grail_plan_analyses.

  What's already shown (step 2 — current stats):
  The page header shows live aggregate counts across all analyzed plans:
  - Total analyzed, entry reached count, success / failure / inconclusive / no_entry
  counts

  The gap:
  The current display gives you raw counts but doesn't make the key ratio obvious, and it
   has no filtering. Specifically missing:

  - Success rate when entry is reached — success / (success + failure + inconclusive) as
  a clear percentage (the most important number for your confidence question)
  - Breakdown by symbol — does SPY hit TP1 more reliably than NVDA?
  - Breakdown by direction — do long plans outperform short plans?
  - Stats filtered to match the current browser filter — right now stats are always
  global, even if you're filtered to one symbol or date range
  - Bars-to-outcome — how quickly does price move to TP1 or stop once the entry zone is
  touched?

✻ Sautéed for 53s

※ recap: Building confidence in grail plan execution by analyzing historical plan
  outcomes. We identified gaps in the current stats display and are about to clarify
  which slices (symbol, direction, date range) matter most before planning improvements.
  (disable recaps in /config)

────────────