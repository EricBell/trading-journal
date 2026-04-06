# Module 4: The Clever Engineering

### Teaching Arc
- **Metaphor:** Think of a master chess player who's solved the same endgame problem a dozen times. They don't recalculate from scratch every move — they recognize the pattern and apply the known solution. The engineers who built this app solved four recurring hard problems with elegant standard techniques. Learning these patterns lets you recognize and request them when talking to AI.
- **Opening hook:** "Four hard problems lurk inside this app. Most developers get them wrong on the first try. Here's how this codebase solves them — and why each solution is the right one."
- **Key insight:** The four patterns — idempotent UPSERT, average cost basis, symbol-scoped reprocessing, and option expiry — appear in nearly every data-intensive application. Knowing their names and how they work makes you dramatically more effective at steering AI.
- **"Why should I care?":** If you can say "use an idempotent UPSERT keyed on (user_id, unique_key)" instead of "make it not create duplicates," AI will write better code faster. This module is vocabulary acquisition as much as technical learning.

### Code Snippets (pre-extracted)

**Idempotent UPSERT** — trading_journal/ingestion.py (lines 308-319):
```python
# Use PostgreSQL UPSERT
stmt = insert(Trade).values(**trade_data)
stmt = stmt.on_conflict_do_update(
    index_elements=['user_id', 'unique_key'],
    set_=dict(
        exec_timestamp=stmt.excluded.exec_timestamp,
        net_price=stmt.excluded.net_price,
        realized_pnl=stmt.excluded.realized_pnl,
        account_id=stmt.excluded.account_id,
        processing_timestamp=stmt.excluded.processing_timestamp
    )
).returning(Trade.trade_id)
```

**Symbol-scoped reprocessing** — trading_journal/ingestion.py (lines 334-338):
```python
# Reprocess positions only for symbols present in this batch.
# Scoping to affected symbols avoids rebuilding the entire position history
# on every upload (which caused worker timeouts with remote PostgreSQL).
affected_symbols = {r.symbol for r in records if r.symbol}
self.position_tracker.reprocess_positions_for_symbols(user_id, affected_symbols)
```

**Average cost basis calculation** — trading_journal/positions.py (lines 151-179):
```python
def _handle_position_open(self, position: Position, trade: Trade) -> None:
    """Handle position opening with average cost basis calculation."""
    if not trade.net_price or not trade.qty:
        logger.warning(f"Missing price or quantity for trade {trade.trade_id}")
        return

    trade_qty = trade.qty
    # Apply contract multiplier for options (100x), futures (e.g. MES=5x), equity (1x)
    multiplier = get_contract_multiplier(trade.instrument_type, trade.symbol or '')
    trade_cost = Decimal(str(trade.net_price)) * abs(trade_qty) * multiplier

    # Determine direction based on side
    if trade.side == "SELL":
        trade_qty = -trade_qty  # Short position

    # Calculate new average cost basis
    if position.current_qty == 0:
        # New position
        position.current_qty = trade_qty
        position.total_cost = trade_cost
        position.avg_cost_basis = Decimal(str(trade.net_price)) * multiplier
```

**Contract multiplier lookup** — trading_journal/positions.py (lines 39-51):
```python
def get_contract_multiplier(instrument_type: str, symbol: str = '') -> Decimal:
    """Get the dollar-per-unit multiplier for the given instrument type.

    - OPTION: 100 (contracts represent 100 shares)
    - FUTURES: point value looked up by root symbol (e.g. MES → $5/point)
    - EQUITY/ETF: 1 (1:1 share price)
    """
    if instrument_type == 'OPTION':
        return Decimal('100')
    if instrument_type == 'FUTURES':
        root = symbol.split()[0].upper() if symbol else ''
        return FUTURES_POINT_VALUES.get(root, Decimal('1'))
    return Decimal('1')
```

### Interactive Elements

- [x] **Code↔English translation** — use the UPSERT snippet. Left: code. Right line-by-line: "Build a SQL INSERT statement. Say: if this exact (user_id + unique_key) already exists... don't create a duplicate — instead UPDATE the existing row with the fresh values. Return the trade_id either way. This is called an 'upsert' — it's an INSERT that turns into an UPDATE when needed."
- [x] **Code↔English translation** (second) — use the symbol-scoped reprocessing snippet. Right: "Build a set of all the stock symbols in this batch (like {AAPL, TSLA, SPY}). Then rebuild positions ONLY for those three symbols — skip the other 200 symbols in your history. This was the fix for a real production bug where rebuilding everything caused a 30-second timeout and the server dropped the request."
- [x] **Group chat animation** — "The 30-second crisis" story. Timeline: [Old code] PositionTracker: "Starting full rebuild... 2,847 fills to process... 28 seconds... 29 seconds..." Gunicorn (the web server): "TIMEOUT. Killing the worker." User: "Why did my upload fail?!" [New code] PositionTracker: "Rebuilding only AAPL, TSLA, SPY from this batch... 0.4 seconds. Done." Gunicorn: "Nice."
- [x] **Pattern cards** — 4 cards, one per engineering pattern:
  - Card 1: **Idempotent UPSERT** — "Upload the same file 10 times, get the same result once. The database fingerprints each row — if it exists, update it; if not, create it."
  - Card 2: **Average Cost Basis** — "When you buy 100 shares at $10 then 100 more at $12, your average cost is $11. Every P&L calculation uses this average, not the price of any individual fill."
  - Card 3: **Symbol-Scoped Reprocessing** — "Only touch the data that changed. Rebuilding all positions on every upload hit a 30-second server timeout. Rebuilding only affected symbols takes milliseconds."
  - Card 4: **Contract Multiplier** — "Options represent 100 shares; futures represent a fixed dollar amount per point. The multiplier table converts 'fill price' into 'actual dollar value.'"
- [x] **Quiz** — 3 questions:
  1. "You bought 200 TSLA at $250 last month, then bought 100 more at $280 today. What's your average cost basis?" (roughly $260 — (200×250 + 100×280) / 300 = $260. Tests understanding of avg cost math.)
  2. "You add support for a new broker. On the first import, a user uploads 3 years of trading history (5,000 fills). Which version of reprocessing should be used?" (Full reprocess, not symbol-scoped — first import needs everything rebuilt. Symbol-scoped is only safe for incremental uploads.)
  3. "You bought 5 TSLA call options at $3.50 each. What's the actual dollar amount at stake?" ($1,750 — 5 contracts × $3.50 × 100 multiplier. Tests understanding of contract multiplier.)

### Reference Files to Read
- `references/interactive-elements.md` → "Code↔English Translations", "Group Chat Animation", "Pattern Cards", "Multiple-Choice Quizzes"
- `references/content-philosophy.md` → always include
- `references/gotchas.md` → always include

### Connections
- **Previous module:** "The Three-Tier Design" — showed the database structure. This module explains the algorithmic patterns used to populate it correctly.
- **Next module:** "The Web Layer" — shifts from the Python engine to the Flask web interface: routes, authentication, templates.
- **Tone/style notes:** Teal accent. Each pattern should feel like a "trick of the trade" worth memorizing. The 30-second timeout story is real and makes a great memorable moment — lean into it.
