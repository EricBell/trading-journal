# Module 1: The Big Picture

### Teaching Arc
- **Metaphor:** A brokerage statement is like a bank's raw transaction ledger — it shows every individual swipe of the card, but not the monthly summary. This app is the accountant who turns thousands of individual swipes into a story: "You spent $400 on groceries, made $900 in trades, and your net worth grew $1,200 this month."
- **Opening hook:** "You've uploaded a CSV and clicked 'Ingest.' Thirty seconds later, you see your win rate, your P&L, your best and worst trades. What just happened?"
- **Key insight:** This app solves a fundamentally hard problem: turning a messy pile of individual "fills" (broker-speak for "the order got executed") into a meaningful trading story. That transformation happens in three automated steps every time you upload a file.
- **"Why should I care?":** Understanding the end-to-end flow means you can tell AI exactly where to add a feature, debug why a number looks wrong, and explain the system to anyone in one sentence.

### Code Snippets (pre-extracted)

**The overall ingestion pipeline call sequence** — trading_journal/ingestion.py (lines 135-141):
```python
if not dry_run and successful_records:
    insert_count, update_count = self._insert_records_with_tracking(
        user_id,
        successful_records,
        str(file_path)
    )
    # Position tracking handled within _insert_records_with_tracking
```

**What happens inside _insert_records_with_tracking** — trading_journal/ingestion.py (lines 334-338):
```python
# Reprocess positions only for symbols present in this batch.
# Scoping to affected symbols avoids rebuilding the entire position history
# on every upload (which caused worker timeouts with remote PostgreSQL).
affected_symbols = {r.symbol for r in records if r.symbol}
self.position_tracker.reprocess_positions_for_symbols(user_id, affected_symbols)
```

**The NdjsonRecord unique_key** — trading_journal/schemas.py (lines 137-153):
```python
@property
def unique_key(self) -> str:
    """Generate unique key for upsert logic."""
    # Use source file, row index, and key trade details
    base_key = f"{self.source_file}:{self.row_index}"

    if self.exec_time:
        base_key += f":{self.exec_time.isoformat()}"
    elif self.time_canceled:
        base_key += f":{self.time_canceled.isoformat()}"

    if self.symbol:
        base_key += f":{self.symbol}"

    if self.side and self.qty:
        base_key += f":{self.side}:{self.qty}"

    return base_key
```

### Interactive Elements

- [x] **Code↔English translation** — use the unique_key snippet: explain each line in plain English. Left: code. Right: "This is the app's fingerprint for each trade — built from the filename, row number, timestamp, and ticker so the same trade uploaded twice never creates a duplicate row."
- [x] **Data flow animation** — actors: [Browser/User, Flask Route `/ingest`, CsvParser, NdjsonIngester, TradeCompletionEngine, PositionTracker, PostgreSQL]. Steps:
  1. User uploads CSV → Flask `/ingest` route receives the file
  2. Flask passes file to CsvParser → parses rows into record dicts
  3. CsvParser output → NdjsonIngester validates and UPSERTs into `trades` table
  4. NdjsonIngester calls → TradeCompletionEngine rebuilds `completed_trades`
  5. NdjsonIngester calls → PositionTracker rebuilds `positions` (only affected symbols)
  6. Flask responds → "47 inserted, 3 updated" shown to user
- [x] **Quiz** — 3 questions, scenario style:
  1. "You upload the same CSV twice by accident. What happens?" (A: Trades are updated, not duplicated — because of the unique_key system. B: Error. C: Duplicates created. D: Nothing.)
  2. "A friend says 'the completed trades table is corrupted.' Should you be worried?" (A: Yes, that data is irreplaceable. B: No — it's fully derived from the `trades` table and can be rebuilt by running process-trades.)
  3. "You added a new stock trade to your latest CSV. Which symbols get their positions recalculated?" (A: All your symbols ever. B: Only the symbols in the uploaded file. C: None — positions update later. D: Only the new symbol.)
- [x] **Group chat animation** — A chat between "You (the trader)" and the app components explaining what's happening during a file upload. Flask says "Got your file!", CsvParser says "Parsed 52 trades", Ingester says "47 new, 5 already existed", TradeEngine says "Found 18 completed round-trips", PositionTracker says "Rebuilt positions for AAPL, TSLA, SPY."

### Reference Files to Read
- `references/interactive-elements.md` → "Group Chat Animation", "Data Flow Animation", "Multiple-Choice Quizzes", "Code↔English Translations"
- `references/content-philosophy.md` → always include
- `references/gotchas.md` → always include
- `references/design-system.md` → color tokens and card styles

### Connections
- **Previous module:** None — this is the first module. Set up the product context and trace one end-to-end flow.
- **Next module:** "The Cast of Characters" — now that learners know what happens, introduce the 6 Python classes responsible for each step.
- **Tone/style notes:** Accent color is teal (#2A7B9B). Call components "actors" not "modules" or "classes." The trader persona is always "you." Never say "the application" — say "the app."
