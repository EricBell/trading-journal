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

  ┌─────────────────────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │                                           Field                                 │                                              Why it matters                                        │
  ├─────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ ATM engaged? (Not used / Entry only / Full session)                             │ Lets you compare ATM-guided vs manual trades over time. This is your biggest unknown right now.    │
  ├─────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Exit reason                                                                     │                                                                                                    │
  │  Hit T1 / Hit T2 / Stopped out / Time stop / Early discretionary / Held too     │ Distinguishes "I followed the plan and stopped out" from "I panicked early." Completely            │
  │ long)                                                                           │ different learning signal.                                                                         │ │                                                                                 │                                                                                                    │
  ├─────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Plan overridden? (Yes/No + reason)                                              │ When you deviated from the plan, was it intentional and why?                                       │
  ├─────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Underlying at entry (options only)                                              │ Manual field for now. Lets us check your entry zone discipline until market data is wired up.      │
  └─────────────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────┘

  Category 2: Automatic enrichment (requires a market data integration — medium effort)

  ┌────────────────────────────────┬───────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────┐
  │              Data              │              Source               │                                        What it unlocks                                         │
  ├────────────────────────────────┼───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Underlying OHLCV at trade time │ Polygon.io free tier / Schwab API │ Entry zone pass/fail for options, high-of-day context                                          │
  ├────────────────────────────────┼───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Did price ever reach T1/T2?    │ Same                              │ True counterfactual: "T1 was reachable and you left it on the table" vs "T1 was never touched" │
  ├────────────────────────────────┼───────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ VIX at trade time              │ Same                              │ Correlate trade performance with volatility regime                                             │
  └────────────────────────────────┴───────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────┘

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
