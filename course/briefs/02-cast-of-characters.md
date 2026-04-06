# Module 2: The Cast of Characters

### Teaching Arc
- **Metaphor:** Think of a production assembly line in a factory — each station does one specific job and passes the work to the next. The CSV enters the factory at one end; a polished dashboard metric exits the other. Six specialized workers (Python classes) are stationed along that line.
- **Opening hook:** "After Module 1, you know *what* happens. Now meet the six Python classes that make it happen — each one has a single job it's obsessed with."
- **Key insight:** Good software has "separation of concerns" — each class knows how to do one thing and trusts the others to do their part. This makes the system easy to test, debug, and extend. When AI writes code for you, it should follow this same principle.
- **"Why should I care?":** When you tell AI "add a feature to X," knowing which class owns X means you can give a precise instruction instead of a vague one. "Update PositionTracker" beats "update the position stuff."

### Code Snippets (pre-extracted)

**CsvParser — parses the account line from row 1** — trading_journal/csv_parser.py (mention this exists; use description — the agent should write this from description since we don't have the exact snippet). 
Actually use this: NdjsonIngester._get_or_create_account — trading_journal/ingestion.py (lines 238-253):
```python
def _get_or_create_account(
    self, session: Session, user_id: int, account_number: str, account_name: Optional[str]
) -> int:
    """Look up or create an Account record, returning its account_id."""
    account = session.query(Account).filter_by(
        user_id=user_id, account_number=account_number
    ).first()
    if not account:
        account = Account(
            user_id=user_id,
            account_number=account_number,
            account_name=account_name,
        )
        session.add(account)
        session.flush()
    return account.account_id
```

**TradeCompletionEngine — the core grouping loop** — trading_journal/trade_completion.py (lines 52-65):
```python
trade_groups: Dict[Any, List[Trade]] = {}
for trade in unlinked_trades:
    key = (trade.symbol, trade.instrument_type, trade.account_id)
    if trade.instrument_type == 'OPTION' and trade.option_data:
        key = key + (trade.exp_date, trade.strike_price, trade.option_type)
    elif trade.instrument_type == 'FUTURES':
        key = key + (trade.exp_date,)
    trade_groups.setdefault(key, []).append(trade)

completed_count = 0
for trades in trade_groups.values():
    completed_count += self._process_trade_group(session, trades)
```

**PositionTracker — average cost math** — trading_journal/positions.py (lines 151-179):
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

### Interactive Elements

- [x] **Code↔English translation** — use the TradeCompletionEngine grouping loop snippet. Left: code. Right: "This loop puts every fill into a 'bucket.' Each bucket is identified by a combination: what symbol, what type of trade (stock vs option vs futures), which account, and (for options) which specific contract. Fills in the same bucket belong to the same round-trip trade."
- [x] **Group chat animation** — 6 actors introduced as "new employees" in a team Slack workspace. CsvParser: "I handle everything about reading your broker's file format. Options/futures sections, column name differences, the account number on line 1 — my problem, not yours." NdjsonIngester: "I'm the gatekeeper. Every record gets validated before it touches the database." TradeCompletionEngine: "I find the buy-sell pairs. When position goes back to zero, I seal a completed trade." PositionTracker: "I do the math. Average cost, P&L, contract multipliers — all me." DashboardEngine: "I crunch your analytics. Win rate, profit factor, streak records." MassiveClient: "I talk to Polygon.io when you need market data — price enrichment, historical bars."
- [x] **Architecture diagram** — visual "assembly line" showing the 6 classes as stations with arrows between them. Files → CsvParser → NdjsonIngester → (TradeCompletionEngine, PositionTracker) → DashboardEngine → Web UI. MassiveClient off to the side as "on call."
- [x] **Quiz** — 3 scenario questions:
  1. "You want AI to change how P&L is calculated when you close a position. Which class should it modify?" (PositionTracker — it owns P&L math)
  2. "A bug causes options trades to be grouped with the wrong symbol. Which class owns the grouping logic?" (TradeCompletionEngine)
  3. "You want to add support for Interactive Brokers CSV files. Which class needs a new counterpart?" (CsvParser — it's the format translator; the rest of the pipeline is already format-agnostic)

### Reference Files to Read
- `references/interactive-elements.md` → "Group Chat Animation", "Multiple-Choice Quizzes", "Code↔English Translations"
- `references/design-system.md` → card styles, icon badges
- `references/content-philosophy.md` → always include
- `references/gotchas.md` → always include

### Connections
- **Previous module:** "The Big Picture" — traced the end-to-end flow. Learners know what happens in order.
- **Next module:** "The Three-Tier Design" — zooms into the database design. The classes write data to three tiers; that's the concept Module 3 unpacks.
- **Tone/style notes:** Teal accent. Keep each class description to 1-2 sentences max. Give each class an "emoji personality" if it helps make them memorable (assembly line visual aids this).
