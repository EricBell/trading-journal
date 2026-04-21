let's work digging into the hg plans and how useful they are.

- hg plans are stored in the grail_files database. The records have the original json and are decomposed into many fields.
- A hg plan has an entry zone, an ideal entry value, a stop zone, a tp1(take profit 1) zone and tp2(take profit 2) zone.
- I want a way to select a hg plan to work on, to analyze.
- The means to select the hg  plan will have a filter mechanism to reduce the candidates I select one from. For instance, by date, by date range, by equite vs option's contrace vs future's contract, by symbol (e.g. spy, msft...)
- When I select one hg plan for analysis, I have a selector for the specific kind of analysis. This implies there will be more than one way to analyze. 
- The first kind of analysis is: 
-- Retrieve 1 min aggregate bar data for the equity. When the plan is for an equity, the equity's data is retrieved (e.g. for msft plan, msft data) and when the plan is for an options contract, the underlying equity is retrieved (e.g. for spy options contract, spy etf data is retrieved). Retrieve data that is missing from the database. To be efficient upsert can be relied on, fetching all the from T-30...T+120.
-- The bar data to retrieve and store is this: the hg plan is created on a date and at a time. use the date and if the created date/time is T, retrieve T-90 through T+120 bars.
-- the bar data is stored in database grail_files, table ohlcv_price_series. Since some/all of the data retrieve at any time may already exist in the table, do the right things to store all the data even if upsert is needed.
-- the analysis of the plan and the data retrieved is:
--- does the data indicate the entry zone was reached?
--- does the data indicate the ideal entry was reached?
--- if the entry zone or ideal entry was reached treat this as the start of the trade.
--- if the trade started what comes first, touching the stop zone or tp1?
what's i'm working to understand is what's the percentage of time the plan succeeded vs failed? Success is the price action reached the entry zone and then reached tp1 before reaching the stop zone. Failure is the priace action reached the entry zone and the reached the stop zone before reaching tp1 zone.
