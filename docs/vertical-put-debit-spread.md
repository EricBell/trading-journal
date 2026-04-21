
## Vertical Put Debit Spread — explanation

A **vertical put debit spread** is a bearish options strategy built with **2 puts on the same underlying and the same expiration**, but with **different strikes**:

- **Buy 1 higher-strike put**
- **Sell 1 lower-strike put**

Because you are paying more for the long put than you collect for the short put, the trade opens for a **net debit**. That debit is your **maximum loss**.

This structure gives you:

- **Defined risk**
- **Defined profit**
- **Bearish exposure**
- Lower cost than buying a put outright

---

## Core mechanics

Let:

- `K1` = higher strike of the long put
- `K2` = lower strike of the short put
- `W = K1 - K2` = spread width
- `D` = net debit paid
- `S_T` = underlying price at expiration

### Expiration payoff per share

- If `S_T >= K1`  
  both puts expire worthless → **P&L = -D**

- If `K2 < S_T < K1`  
  the spread has partial intrinsic value → **P&L = (K1 - S_T) - D**

- If `S_T <= K2`  
  the spread is fully in the money → **P&L = W - D**

### Key formulas

| Metric | Formula |
|---|---|
| Spread width | `W = K1 - K2` |
| Max loss | `D` |
| Max profit | `W - D` |
| Breakeven at expiration | `K1 - D` |
| Contract P&L | `per-share P&L × 100` |

---

## What the backtest should do

If Claude Code is building a backtest from **historical market data**, the program should treat the spread as a **real options position** built from historical option quotes or another historical options data source.

### Recommended backtest design

#### 1) Separate signal logic from spread logic
The entry signal should be independent from the options pricing and payoff logic.

Examples of entry signals:

- bearish breakout
- breakdown below support
- moving-average cross
- RSI weakness
- volatility expansion
- custom setup from your strategy rules

#### 2) Avoid lookahead bias
The backtest must only use information available at the time of the trade.

That means:

- generate the signal on bar `t`
- enter on bar `t+1` or at a clearly defined execution time
- never use future bars to choose strikes, entries, or exits

#### 3) Use actual historical option data when possible
For the cleanest backtest, Claude should use historical option quotes or historical chain snapshots to determine:

- long leg price
- short leg price
- spread debit at entry
- spread value at exit

This is much better than trying to infer prices only from the underlying.

#### 4) Parameterize the trade rules
Claude should make these inputs configurable:

- ticker or underlying
- expiration selection
- strike selection rule
- spread width
- entry signal
- stop loss
- take profit
- time stop
- commission
- slippage
- exit condition

---

## Best-practice assumptions

Tell Claude Code to make the assumptions explicit:

### Use historical option quotes for pricing
If available, base the trade on actual historical option prices rather than theoretical estimates.

### Use underlying price only for signal generation and strike selection
The underlying should drive the setup logic, but the spread value itself should come from the historical options data.

### Keep pricing and signal data separate
Do not mix signal calculations with option valuation in a way that creates bias.

### Include transaction costs
A realistic backtest should include:

- commissions
- spread/slippage
- potential liquidity friction

### Handle assignment risk if needed
For a first pass, you can ignore early assignment risk, but the code should note that limitation.

---

## What Claude should calculate

For every trade, the backtest should record:

- ticker
- entry date
- exit date
- long strike
- short strike
- expiration date
- entry debit
- exit spread value
- P&L per share
- P&L dollars
- return on risk
- exit reason

And performance metrics such as:

- total trades
- win rate
- average win
- average loss
- expectancy
- profit factor
- max drawdown
- average hold time
- average return on risk
- percent of max profit captured

---

## Copy-paste prompt for Claude Code

Here’s a cleaner prompt you can give Claude:

```text
Build a Python backtesting module for vertical put debit spreads using historical market data and historical options data.

Strategy definition:
- A vertical spread uses the same underlying and the same expiration.
- A vertical put debit spread (bear put spread) means:
  1) buy 1 put at the higher strike K1
  2) sell 1 put at the lower strike K2
  3) both legs must share the same expiration
  4) the trade is entered for a net debit D > 0

Core payoff rules:
- Width W = K1 - K2
- Max loss = D
- Max profit = W - D
- Breakeven at expiration = K1 - D
- Per-contract dollar P&L = per-share P&L * 100

Expiration payoff per share:
- If ST >= K1: P&L = -D
- If K2 < ST < K1: P&L = (K1 - ST) - D
- If ST <= K2: P&L = W - D

Backtest requirements:
1) Use historical underlying data for signal generation and strike selection.
2) Use historical options data or historical chain snapshots for pricing the spread.
3) Avoid lookahead bias:
   - signals must be generated from information available at time t
   - entries should occur at t+1 open or another explicitly defined execution time
4) Keep strategy logic separate from pricing logic.
5) Parameterize:
   - ticker list
   - signal rules
   - target DTE
   - strike selection rule
   - spread width
   - take profit
   - stop loss
   - time stop
   - commission per contract
   - slippage
6) Support 2 modes:
   - hold-to-expiration payoff mode
   - daily mark-to-market mode

If historical option quotes are available:
- Use actual bid/ask, midpoint, or trade prices as configured.
- Compute the spread value as long_put_price - short_put_price.

If only historical option chains are available:
- Use the available chain snapshot to build the spread at entry and exit.
- Make assumptions explicit in the output.

Trade record fields:
- ticker
- entry_date
- exit_date
- entry_underlying_price
- exit_underlying_price
- long_strike
- short_strike
- expiration_date
- debit_paid
- exit_spread_value
- pnl_per_share
- pnl_dollars
- return_on_risk
- exit_reason

Performance metrics to output:
- total trades
- win rate
- average win
- average loss
- expectancy
- profit factor
- max drawdown
- average hold time
- average return on risk
- percent of max profit captured

Implementation preferences:
- Use pandas and numpy.
- Use scipy.stats.norm if a theoretical pricing model is needed.
- Write clean, modular code with functions or classes for:
  - data loading
  - signal generation
  - strike selection
  - option pricing
  - trade simulation
  - performance reporting
- Include comments explaining the assumptions and limitations.
- Add a warning or metadata flag whenever the results depend on historical options data quality, midpoint pricing, or modeled prices.

Validation tests:
- Verify the payoff at expiration matches the piecewise formula exactly.
- Verify max loss cannot exceed debit paid.
- Verify max profit cannot exceed spread width minus debit.
- Verify no lookahead bias in entries.
- Verify per-contract P&L equals per-share P&L times 100.

Deliver a backtester that is honest about the data source and can be extended later if a more complete historical options feed is added.
```

---

## Short version

If you want Claude to build this correctly, the key idea is:

- **use historical underlying data for signals**
- **use historical options data for spread pricing**
- **do not reconstruct option prices from a modern chain**
- **keep the payoff math explicit and defined-risk**

