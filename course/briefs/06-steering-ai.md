# Module 6: Steering the AI

### Teaching Arc
- **Metaphor:** A ship's navigator uses charts, instruments, and landmarks to course-correct in real time. They don't control the engine or the rudder directly — but they know where the rocks are, where the currents run, and how to read the compass. You're the navigator. The AI is the engine room. This module gives you the chart.
- **Opening hook:** "You've now seen how every part of this app works. Module 6 is about using that knowledge as a superpower — to give AI better instructions, catch its mistakes, and make smarter decisions about what to build next."
- **Key insight:** The most valuable thing you can do with technical knowledge isn't write code — it's make better decisions. Knowing the architecture means you can say "this belongs in TradeCompletionEngine, not the route handler" and be right. Knowing the known limitations means you can ask AI to solve the *right* problem.
- **"Why should I care?":** Everything in this course leads here. You spent 5 modules learning how the app works. Now spend Module 6 practicing the actual skill: translating that understanding into precise AI instructions.

### Code Snippets (pre-extracted)

**The known limitation: full rebuild bottleneck** — trading_journal/trade_completion.py (lines 25-29):
```python
def reprocess_all_completed_trades(self, user_id: int) -> Dict[str, Any]:
    """Clear and rebuild all completed trades for a user from scratch."""
    with self.db_manager.get_session() as session:
        # Unlink all executions from their completed trades
        session.query(Trade).filter(Trade.user_id == user_id).update(
```

This is documented as a known future bottleneck in OVERVIEW.md §10: "TradeCompletionEngine.reprocess_all_completed_trades always rebuilds all completed trades for the user, not just affected symbols. This is fast enough currently but will become a bottleneck at large trade volumes."

**The three-tier constraint on new features** — if you add a new field to completed_trades, remember that the table is *destroyed and rebuilt* on every ingest. The field must either be derived from the fills (Tier 1), or it must live in trade_annotations (separate table, survives rebuilds).

**Configuration priority** — trading_journal/config.py. Priority: env vars → profile → app config → shared postgres config → legacy .env → defaults. When telling AI to "add a new config option," it should follow this priority chain.

### Interactive Elements

- [x] **Group chat animation** — "Before and After" side-by-side conversations with AI:
  BEFORE: "Add a feature where I can save a risk/reward ratio for each trade."
  AI: "I'll add a risk_reward column to completed_trades." ← WRONG — gets wiped on rebuild.
  
  AFTER: "Add a risk_reward_ratio field to trade_annotations, not completed_trades. trade_annotations survives the full rebuild because it uses a natural key (user_id, symbol, opened_at). Add an input to the trade detail annotation form."
  AI: "Got it — adding to trade_annotations with the natural key constraint." ← CORRECT.
- [x] **Pattern cards** — "Known Limitations" deck (4 cards):
  - **Full rebuild bottleneck** — TradeCompletionEngine rebuilds ALL completed trades on every upload. Works fine now; will slow down at scale. Fix: scope to affected symbols, like PositionTracker already does.
  - **Single broker format** — CsvParser understands only Schwab CSV. New brokers need a new parser class that outputs the same NdjsonRecord schema.
  - **No live data** — Everything is file-import only. No connection to live broker APIs. Historical OHLCV comes from Polygon.io on demand.
  - **Annotation re-linking is best-effort** — If two trades for the same symbol open at exactly the same millisecond, one annotation might re-link to the wrong trade.
- [x] **Quiz** — 4 "what would you tell AI" scenario questions:
  1. "You want to add a 'confidence score' (1-5) you enter manually per trade. Where does it go and why?" (trade_annotations — it's manually entered, must survive the completed_trades rebuild)
  2. "A user reports their positions are wrong after uploading a CSV with 10 symbols. But your terminal shows the upload succeeded. Where do you look first?" (Check PositionTracker logs for the 10 symbols in the upload — symbol-scoped reprocessing only touches those symbols, so a bug there would explain it)
  3. "You want to add support for TD Ameritrade CSV files. What's the minimum change needed?" (Write a new parser class that accepts TD Ameritrade format and outputs the same NdjsonRecord schema — the rest of the pipeline is already format-agnostic)
  4. "AI suggests adding a `win_rate` column to the `users` table, updated on every trade. Is this a good idea?" (No — win_rate is a derived metric, not source data. It should be calculated on demand by DashboardEngine, not stored. Storing derived data in Tier 1 or users would make it stale and require constant maintenance.)
- [x] **Data flow animation** — "Adding a new feature: the checklist." Animate through: (1) Identify which tier the data lives in → (2) Pick the right class to own the logic → (3) If user-entered: use trade_annotations; if derived: use completed_trades → (4) Update the web route + template → (5) Add a migration for any new DB column. Each step highlights the relevant part of the architecture diagram from Module 2.

### Reference Files to Read
- `references/interactive-elements.md` → "Group Chat Animation", "Pattern Cards", "Data Flow Animation", "Multiple-Choice Quizzes"
- `references/content-philosophy.md` → always include
- `references/gotchas.md` → always include

### Connections
- **Previous module:** "The Web Layer" — completed the full architecture tour. All 6 actors, all 3 tiers, all 4 engineering patterns, and the full web layer are now understood.
- **Next module:** None — this is the final module. End with a summary card: "You now know how to navigate this codebase. Here's your cheat sheet."
- **Tone/style notes:** Teal accent. This module should feel like a graduation — practical, empowering, slightly celebratory. The final screen should be a "navigator's chart" reference card with the key architectural facts in one view: the 6 actors, the 3 tiers, the 4 patterns, the 10 routes.
