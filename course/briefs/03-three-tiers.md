# Module 3: The Three-Tier Data Hierarchy

### Teaching Arc
- **Metaphor:** Think of it like a ship's navigation system with three instruments: a raw GPS log (every position fix, every second), a plotted route summary (departure → arrival, distance, speed), and a current position indicator (where you are right now). Each instrument is derived from the raw GPS log but serves a completely different purpose. You can always regenerate the summary and the current position from the raw log — the raw log is the only thing you must never lose.
- **Opening hook:** "The database has 13 tables, but only three of them form the spine of the whole system. Everything else supports this central architecture."
- **Key insight:** Tiers 2 and 3 (completed_trades and positions) are fully *derived* from Tier 1 (the raw fills). This means you can delete them and rebuild them at any time. The only data you can't reconstruct is the raw fills — and the manual annotations you add (patterns, notes, stop prices).
- **"Why should I care?":** This design principle — "keep the source data pure; derive everything else" — is one of the most important patterns in data engineering. Understanding it helps you recognize when AI is designing things correctly vs. making them fragile.

### Code Snippets (pre-extracted)

**The rebuild process — deletes all completed trades then rebuilds from scratch** — trading_journal/trade_completion.py (lines 26-36):
```python
def reprocess_all_completed_trades(self, user_id: int) -> Dict[str, Any]:
    """Clear and rebuild all completed trades for a user from scratch."""
    with self.db_manager.get_session() as session:
        # Unlink all executions from their completed trades
        session.query(Trade).filter(Trade.user_id == user_id).update(
            {Trade.completed_trade_id: None}, synchronize_session=False
        )
        # Delete all completed trades for this user
        session.query(CompletedTrade).filter(
            CompletedTrade.user_id == user_id
        ).delete(synchronize_session=False)
        session.commit()
```

**Annotation re-linking after rebuild** — trading_journal/trade_completion.py (lines 67-84):
```python
# Re-link any annotations that were orphaned by the completed_trades rebuild.
# The natural key (user_id, symbol, opened_at) ties each annotation back to
# its newly-created completed_trade row so they are never left with a NULL FK.
with self.db_manager.get_session() as session:
    session.execute(
        text("""
            UPDATE trade_annotations ta
            SET completed_trade_id = ct.completed_trade_id
            FROM completed_trades ct
            WHERE ta.user_id   = :user_id
              AND ta.completed_trade_id IS NULL
              AND ct.user_id   = :user_id
              AND ta.symbol    = ct.symbol
              AND ta.opened_at = ct.opened_at
        """),
        {"user_id": user_id},
    )
    session.commit()
```

**The unique_key for idempotent UPSERT** — trading_journal/schemas.py (lines 137-153):
```python
@property
def unique_key(self) -> str:
    """Generate unique key for upsert logic."""
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

- [x] **Code↔English translation** — use the annotation re-linking SQL snippet. Left: the SQL UPDATE. Right: "After every rebuild, annotations (the notes and patterns you typed in) need to be reconnected to the new completed_trade rows. This SQL does that by matching on three things that never change: your user ID, the stock symbol, and the exact timestamp the trade opened. It's like reuniting luggage with its owner by matching name, destination, and flight number."
- [x] **Data flow animation** — show the three tiers as stacked horizontal layers. Animate: "File uploaded → fills pour into Tier 1 (trades table) → Tier 2 rebuilds itself from Tier 1 → Tier 3 rebuilds itself from Tier 1 → Annotations survive the rebuild." Show a red ❌ striking through Tier 2 (deleted), then a green rebuild arrow from Tier 1. Show trade_annotations floating beside and then re-attaching.
- [x] **Group chat animation** — TradeCompletionEngine: "I'm about to delete everything in completed_trades." Annotation: "Wait, what about me? I'm stored there!" TradeCompletionEngine: "You're safe — you live in a separate table (trade_annotations) with a backup ID: (user, symbol, opened_at). I'll reconnect you after the rebuild." Annotation: "...oh. Okay. Good system." PositionTracker: "Same thing happened to me last week with positions. Tier 1 never lies."
- [x] **Quiz** — 4 questions:
  1. "You run `db process-trades` by mistake and it takes a long time. Are your P&L numbers in danger?" (No — process-trades rebuilds Tier 2 from Tier 1, which is read-only source data)
  2. "You annotated 50 trades with patterns like 'MACD Scalp.' You then re-upload a corrected CSV. Will those annotations survive?" (Yes — annotations use a natural key, not a foreign key that gets deleted)
  3. "Which table would you NEVER want to accidentally delete?" (trades — it's Tier 1, the source of truth. Everything else can be rebuilt.)
  4. "A developer wants to add a 'trade quality score' that you manually enter. Should it go in completed_trades or trade_annotations?" (trade_annotations — because completed_trades is destroyed and rebuilt on every ingest)

### Reference Files to Read
- `references/interactive-elements.md` → "Data Flow Animation", "Group Chat Animation", "Multiple-Choice Quizzes", "Code↔English Translations"
- `references/content-philosophy.md` → always include
- `references/gotchas.md` → always include

### Connections
- **Previous module:** "The Cast of Characters" — introduced the 6 Python classes that read/write the database.
- **Next module:** "The Clever Engineering" — zooms in on specific technical decisions (average cost basis, idempotent UPSERT, symbol-scoped reprocessing).
- **Tone/style notes:** Teal accent. Emphasize the word "derived" — it's the key term. Use "Tier 1/2/3" consistently, matching the OVERVIEW.md terminology. The `trade_annotations` table is the "survivor" — it's the only user-entered data that persists across rebuilds.
