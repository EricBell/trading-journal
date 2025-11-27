# Product Requirements Document (PRD)

# 📈 Trading Journal: Data Ingestion and Core Storage

**Version:** 1.0 (MVP - Validated)
**Last Updated:** 2025-11-26
**Status:**

- 📝 **VALIDATED** - Requirements validated against actual converter output and trading best practices
- ⏳ **PHASE 1 (TDD)** - Ready for implementation with comprehensive technical specifications

**Implementation Summary (Target):**

**Version 1.0 (Core Data Model & MVP Reporting):**

- 🎯 Functional Requirements: 100% target
- 🎯 Non-Functional Requirements: 100% target
- 🎯 Success Metrics: 100% target
- 🎯 Reporting: Core dashboard metrics and daily trade log implemented

-----

## 1. Overview

### Problem Statement

Day traders require a dedicated, centralized application to analyze their performance across multiple trading platforms. While the existing **Schwab CSV to JSON Converter** successfully processes raw data, traders still lack an integrated, relational application to:

1. **Persist and Centralize** NDJSON trade data into a single, query-optimized PostgreSQL database.
2. **Normalize and Relate** orders and executions across different instrument types (Equities and Options).
3. Provide immediate **analytical value** through essential performance metrics (P&L, Win/Loss Ratio) via an MVP dashboard.

Manual aggregation limits analytical depth and makes crucial performance analysis difficult and time-consuming.

### Goal

Create a **PostgreSQL-based backend data ingestion service** that consumes standardized NDJSON trade files (initially from ThinkOrSwim) and an **MVP Reporting Interface** to display core performance metrics. The architecture must be robust, extensible, and designed to integrate future granular historical price data.

### Non-Goals

- **Not a Data Converter:** Does not handle the conversion of raw CSV files; it strictly consumes pre-converted NDJSON.
- **Not a Live Trading Tool:** Does not connect to live or historical platform APIs (e.g., ThinkOrSwim, NinjaTrader). All data is based on file imports.
- **Not a Charting Application (in MVP):** Does not include complex visualization using charting packages (e.g., TradingView). This is a **Future Enhancement (Section 9)**.

-----

## 2. Background & Context

### Current Situation

Traders manually run the CSV-to-JSON converter, resulting in clean NDJSON files for each day/account. They currently trade **Equities and Options** almost daily. These files are ready for ingestion but lack a unified, relational storage mechanism required for cross-trade and long-term analysis.

### Data Ingestion Source

The primary input is **NDJSON files** created by the existing Schwab CSV converter project. These files contain records with normalized fields and support both equity and options trading data.

### Technical Environment

- **Database**: PostgreSQL 14+ (JSONB support, performance optimization)
- **Input Format**: NDJSON (Newline Delimited JSON)
- **Development Approach**: TDD (Test-Driven Development) with comprehensive unit testing
- **Technology Stack**: Python 3.11+, SQLAlchemy 2.0, Click CLI framework

### Use Cases

1. **Historical Data Archive**: Persist all trade history in a searchable, relational format.
2. **Daily Performance Review**: Quickly review the day's performance via key metrics like Net P&L and Win/Loss Ratio upon data ingestion.
3. **Position Tracking**: Real-time position balances and P&L calculations using average cost basis methodology.
4. **Future Granularity Integration**: The data model must support linking trade executions to high-granularity (sub-daily) OHLCV data when it becomes available.

-----

## 3. Requirements

### 3.1 Functional Requirements

#### F.1 Ingestion and File Handling

- [ ] **F.1.1** The service must read one or more **NDJSON files** containing trade records.
- [ ] **F.1.2** Must validate the schema of each NDJSON record against the expected input schema (Section 4).
- [ ] **F.1.3** Must perform **UPSERT** logic based on a unique trade identifier to prevent duplicate records upon re-import.
- [ ] **F.1.4** Support batch processing of multiple files with source file tracking and audit trail.

#### F.2 Data Modeling and Persistence

- [ ] **F.2.1** Trades must be stored relationally in PostgreSQL, with a schema optimized for both Equities and Options.
- [ ] **F.2.2** Must handle pre-converted ISO-8601 timestamps from the converter without additional processing.
- [ ] **F.2.3** Must automatically persist the instrument type for each record (**EQUITY**, **OPTION**) based on the `asset_type` field from converter. STOCK and ETF both map to EQUITY instrument_type.
- [ ] **F.2.4** Must store all event types: **fill**, **cancel**, **amend** for complete trade lifecycle tracking.
- [ ] **F.2.5** Must preserve all source metadata including `source_file`, `source_file_index`, and complete `raw` data for audit trail.

#### F.3 Position Tracking & P&L Calculation

- [ ] **F.3.1** Maintain real-time position balances per symbol using **average cost basis** methodology.
- [ ] **F.3.2** Calculate **realized P&L** on position close (TO CLOSE transactions) using average cost basis.
- [ ] **F.3.3** Handle **partial position closes** with proper cost basis allocation.
- [ ] **F.3.4** Track **open positions** separately from closed positions for reporting.
- [ ] **F.3.5** Support both equity and options position tracking with appropriate option-specific data.

#### F.4 MVP Reporting and Filtering

- [ ] **F.4.1** Implement the Core Dashboard metrics (Section 6.1).
- [ ] **F.4.2** Implement the Daily Trade Log report (Section 6.2).
- [ ] **F.4.3** Implement basic filtering based on **Timeframe**, **Platform**, and **Instrument Type**.
- [ ] **F.4.4** Provide **open positions** report showing current holdings and unrealized P&L.

#### F.5 Advanced Data Handling

- [ ] **F.5.1** Process amendment records to update existing trade entries appropriately.
- [ ] **F.5.2** Handle multi-leg option spread orders maintaining strategy context via `spread` field.
- [ ] **F.5.3** Support multiple account/portfolio separation (future-ready architecture).
- [ ] **F.5.4** Maintain comprehensive audit trail with file processing history.

#### F.6 Trading Pattern Analysis & Notes

- [ ] **F.6.1** Support optional **setup pattern annotation** for each completed trade (MVP: free text field).
- [ ] **F.6.2** Allow post-trade annotation of setup patterns for completed round-trip trades via CLI interface.
- [ ] **F.6.3** Generate **setup pattern performance reports** showing P&L by pattern type across completed trades.
- [ ] **F.6.4** **Production Version**: Implement managed dropdown with predefined setup patterns.
- [ ] **F.6.5** Support optional **trade notes** field for capturing thoughts, emotions, and trade analysis on completed trades.
- [ ] **F.6.6** Allow post-trade note entry and editing for completed trades via CLI interface.
- [ ] **F.6.7** Include trade notes in detailed trade reports and export capabilities.

### 3.2 Non-Functional Requirements

#### N.1 Performance

- [ ] **N.1.1** The ingestion service must process and persist **10,000 trade records in under 5 seconds**.
- [ ] **N.1.2** Database schema must be optimized with proper indexing for fast read access for daily/weekly reporting queries.
- [ ] **N.1.3** **Dashboard query response time < 500ms** for 1-year data.
- [ ] **N.1.4** **Memory usage < 500MB** for batch processing 1000+ files.

#### N.2 Usability (Ingestion Tool)

- [ ] **N.2.1** The service must be executable via a comprehensive **Command-Line Interface (CLI)**.
- [ ] **N.2.2** Provide clear, progress-based output during ingestion (e.g., "Processing file X of Y... 100 records inserted/updated").
- [ ] **N.2.3** Support **dry-run** mode for testing imports without database changes.

#### N.3 Reliability and Error Handling

- [ ] **N.3.1** Must use **database transactions** to ensure that entire file imports succeed or fail atomically.
- [ ] **N.3.2** Log all schema validation errors and database failures, reporting the specific line number and file name.
- [ ] **N.3.3** Implement **retry logic** with exponential backoff for database connection failures.
- [ ] **N.3.4** **Recovery time < 30 seconds** from database connection failures.

#### N.4 Maintainability and Development

- [ ] **N.4.1** **Test-Driven Development (TDD):** All implementation work must follow TDD methodology.
- [ ] **N.4.2** **Unit Testing:** All core components (ingestion logic, data normalization, P&L calculation) must be covered by comprehensive unit tests.
- [ ] **N.4.3** **Project Phasing:** Implementation follows clear phases with defined milestones (Section 8).

#### N.5 Data Integrity & Consistency

- [ ] **N.5.1** Implement database constraints ensuring position balances are mathematically consistent.
- [ ] **N.5.2** Provide data reconciliation reports comparing file data to database totals.
- [ ] **N.5.3** **99.9% data ingestion accuracy** validated against source files.
- [ ] **N.5.4** **Zero P&L calculation discrepancies** on closed positions.

#### N.6 Monitoring & Observability

- [ ] **N.6.1** Log detailed performance metrics: records/second, memory usage, SQL query times.
- [ ] **N.6.2** Implement health checks for database connectivity and schema version.
- [ ] **N.6.3** Provide import summary reports with error counts and processing statistics.

-----

## 4. Data Schema

### 4.1 Input Schema (Validated Against Actual Converter Output)

The input is NDJSON from the existing Schwab converter. Each line represents a trade execution, cancellation, or amendment:

**Equity Example:**
```json
{
  "section": "Filled Orders",
  "row_index": 10,
  "exec_time": "2025-11-04T10:17:00",
  "side": "BUY",
  "qty": 300,
  "pos_effect": "TO OPEN",
  "symbol": "RANI",
  "exp": null,
  "strike": null,
  "type": "STOCK",
  "spread": "STOCK",
  "price": 2.489,
  "net_price": 2.489,
  "price_improvement": 0.3,
  "order_type": "MKT",
  "event_type": "fill",
  "asset_type": "STOCK",  // Valid values: STOCK, OPTION, ETF
  "option": null,
  "source_file": "2025-11-04-TradeActivity.csv",
  "source_file_index": 0,
  "raw": "original CSV row data",
  "issues": []
}
```

**Options Example:**
```json
{
  "section": "Canceled Orders",
  "row_index": 11,
  "time_canceled": "2025-10-21T15:59:39",
  "side": "BUY",
  "qty": 3,
  "pos_effect": "TO OPEN",
  "symbol": "SPY",
  "exp": "2025-10-21",
  "strike": 673.0,
  "type": "CALL",
  "spread": "SINGLE",
  "price": null,
  "event_type": "cancel",
  "asset_type": "OPTION",
  "option": {
    "exp_date": "2025-10-21",
    "strike": 673.0,
    "right": "CALL"
  },
  "source_file": "2025-10-21-TradeActivity.csv",
  "raw": "original CSV row data",
  "issues": []
}
```

**ETF Example:**
```json
{
  "section": "Filled Orders",
  "row_index": 12,
  "exec_time": "2025-11-25T10:08:24",
  "side": "BUY",
  "qty": 100,
  "pos_effect": "TO OPEN",
  "symbol": "SPY",
  "exp": null,
  "strike": null,
  "type": "STOCK",
  "spread": "STOCK",
  "price": 450.00,
  "net_price": 450.00,
  "price_improvement": 0.0,
  "order_type": "MKT",
  "event_type": "fill",
  "asset_type": "ETF",
  "option": null,
  "source_file": "2025-11-25-TradeActivity.csv",
  "source_file_index": 0,
  "raw": "original CSV row data",
  "issues": []
}
```

**Note**: ETF asset_type maps to EQUITY instrument_type in the database, treated identically to STOCK for P&L calculations.

### 4.2 Trade Hierarchy & Terminology

#### Definitions

**EXECUTION (trades table)**: Individual broker order fills/executions
- Single order execution event from the broker
- Includes partial fills, cancellations, amendments
- Examples: "BUY 100 AAPL at $150.25", "SELL 50 AAPL at $151.00"
- Source: Direct from NDJSON converter output

**TRADE (completed_trades table)**: Complete round-trip business transactions
- Conceptual trading unit with entry and exit
- Composed of one or more executions
- Examples: "AAPL swing trade (net +100 shares, entry avg $150.50, exit avg $155.25)"
- Contains: Setup patterns, notes, strategy analysis

**POSITION (positions table)**: Current holdings aggregate
- Running totals across all trades for a symbol
- Real-time position tracking with average cost basis
- Examples: "Currently long 500 AAPL shares at $148.75 average cost"

#### Relationships
- Multiple **executions** → One **completed trade**
- Multiple **completed trades** → One **position** (for a symbol)

### 4.3 Output Database Schema (PostgreSQL)

#### `trades` Table (Individual Executions/Fills)

| Field Name | Data Type | Description | Notes |
|:---|:---|:---|:---|
| `trade_id` | `BIGSERIAL` | Primary Key | |
| `unique_key` | `TEXT` | Unique hash for UPSERT logic | UNIQUE constraint |
| | | | |
| **Execution Details** | | | |
| `exec_timestamp` | `TIMESTAMP WITH TIME ZONE` | ISO-8601 execution time | From converter |
| `event_type` | `VARCHAR(10)` | fill, cancel, amend | **New field** |
| | | | |
| **Instrument Details** | | | |
| `symbol` | `VARCHAR(50)` | Stock/Option base symbol | |
| `instrument_type` | `VARCHAR(10)` | EQUITY or OPTION | From `asset_type` |
| | | | |
| **Trade Details** | | | |
| `side` | `VARCHAR(10)` | BUY or SELL | |
| `qty` | `INTEGER` | Quantity (signed) | |
| `pos_effect` | `VARCHAR(10)` | TO OPEN or TO CLOSE | |
| | | | |
| **Pricing** | | | |
| `price` | `NUMERIC(18, 8)` | Limit/Order Price | |
| `net_price` | `NUMERIC(18, 8)` | Actual Execution Price | For P&L calculation |
| `price_improvement` | `NUMERIC(18, 8)` | Price improvement amount | |
| `order_type` | `VARCHAR(10)` | MKT, LMT, STP, etc. | |
| | | | |
| **Options Data** | | | |
| `exp_date` | `DATE` | Option Expiration Date | NULL for Equities |
| `strike_price` | `NUMERIC(18, 4)` | Option Strike Price | NULL for Equities |
| `option_type` | `VARCHAR(4)` | CALL or PUT | NULL for Equities |
| `spread_type` | `VARCHAR(20)` | SINGLE, STOCK, VERTICAL, etc. | **New field** |
| `option_data` | `JSONB` | Complete option details | **New field** |
| | | | |
| **Processing Metadata** | | | |
| `platform_source` | `VARCHAR(20)` | TOS (ThinkOrSwim) | Default 'TOS' |
| `source_file_path` | `TEXT` | Source NDJSON file path | **New field** |
| `source_file_index` | `INTEGER` | Batch processing index | **New field** |
| `raw_data` | `TEXT` | Original CSV row | Audit trail |
| `processing_timestamp` | `TIMESTAMP WITH TIME ZONE` | When record was processed | Default NOW() |
| | | | |
| **P&L Tracking** | | | |
| `realized_pnl` | `NUMERIC(18, 8)` | Calculated on execution close | **New field** |
| | | | |
| **Trade Relationship** | | | |
| `completed_trade_id` | `BIGINT` | FK to completed_trades | **New field** - Links executions to complete trades |

#### `completed_trades` Table (Complete Round-Trip Trades - New)

| Field Name | Data Type | Description | Notes |
|:---|:---|:---|:---|
| `completed_trade_id` | `BIGSERIAL` | Primary Key | |
| `symbol` | `VARCHAR(50)` | Stock/Option base symbol | |
| `instrument_type` | `VARCHAR(10)` | EQUITY or OPTION | |
| `option_details` | `JSONB` | Option-specific data | NULL for equities |
| | | | |
| **Trade Summary** | | | |
| `total_qty` | `INTEGER` | Net quantity traded | |
| `entry_avg_price` | `NUMERIC(18, 8)` | Average entry price | Calculated from executions |
| `exit_avg_price` | `NUMERIC(18, 8)` | Average exit price | Calculated from executions |
| `gross_proceeds` | `NUMERIC(18, 8)` | Total proceeds from exits | |
| `gross_cost` | `NUMERIC(18, 8)` | Total cost of entries | |
| `net_pnl` | `NUMERIC(18, 8)` | Realized P&L for complete trade | |
| | | | |
| **Trade Timeline** | | | |
| `opened_at` | `TIMESTAMP WITH TIME ZONE` | First execution timestamp | |
| `closed_at` | `TIMESTAMP WITH TIME ZONE` | Last execution timestamp | |
| `hold_duration` | `INTERVAL` | Time between open and close | |
| | | | |
| **Trading Analysis** | | | |
| `setup_pattern` | `TEXT` | Trading setup/pattern annotation | **MVP: free text, Production: managed dropdown** |
| `trade_notes` | `TEXT` | Optional trade notes/thoughts | **Supports short phrases to multi-paragraph entries** |
| `strategy_category` | `VARCHAR(30)` | Strategy type | e.g., "Scalp", "Swing", "Day Trade" |
| | | | |
| **Trade Classification** | | | |
| `is_winning_trade` | `BOOLEAN` | Whether trade was profitable | Calculated from net_pnl |
| `trade_type` | `VARCHAR(20)` | LONG or SHORT | Based on entry direction |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | Record creation time | Default NOW() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | Last update time | Default NOW() |

#### `positions` Table (Position Tracking - New)

| Field Name | Data Type | Description | Notes |
|:---|:---|:---|:---|
| `position_id` | `BIGSERIAL` | Primary Key | |
| `symbol` | `VARCHAR(50)` | Stock/Option base symbol | |
| `instrument_type` | `VARCHAR(10)` | EQUITY or OPTION | |
| `option_details` | `JSONB` | Option-specific data | NULL for equities |
| | | | |
| **Position State** | | | |
| `current_qty` | `INTEGER` | Current position size | Can be negative |
| `avg_cost_basis` | `NUMERIC(18, 8)` | Average cost per share | |
| `total_cost` | `NUMERIC(18, 8)` | Total cost basis | |
| | | | |
| **Timestamps** | | | |
| `opened_at` | `TIMESTAMP WITH TIME ZONE` | First trade timestamp | |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | Last modification | |
| `closed_at` | `TIMESTAMP WITH TIME ZONE` | Position close time | NULL if open |
| | | | |
| **P&L Tracking** | | | |
| `realized_pnl` | `NUMERIC(18, 8)` | Cumulative realized P&L | Default 0 |

#### `processing_log` Table (Audit Trail - New)

| Field Name | Data Type | Description | Notes |
|:---|:---|:---|:---|
| `log_id` | `BIGSERIAL` | Primary Key | |
| `file_path` | `TEXT` | Processed file path | |
| `processing_started_at` | `TIMESTAMP WITH TIME ZONE` | Processing start | Default NOW() |
| `processing_completed_at` | `TIMESTAMP WITH TIME ZONE` | Processing completion | NULL if failed |
| `records_processed` | `INTEGER` | Successfully processed | Default 0 |
| `records_failed` | `INTEGER` | Failed records | Default 0 |
| `status` | `VARCHAR(20)` | processing, completed, failed | |
| `error_message` | `TEXT` | Failure details | NULL if successful |

#### `setup_patterns` Table (Production Version - Web UI)

| Field Name | Data Type | Description | Notes |
|:---|:---|:---|:---|
| `pattern_id` | `BIGSERIAL` | Primary Key | |
| `pattern_name` | `VARCHAR(50)` | Setup pattern name | e.g., "MACD Scalp", "5min ORB" |
| `pattern_description` | `TEXT` | Detailed description | Optional |
| `pattern_category` | `VARCHAR(30)` | Pattern category | e.g., "Scalp", "Swing", "Breakout" |
| `is_active` | `BOOLEAN` | Pattern availability | Default TRUE |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | Creation timestamp | Default NOW() |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | Last update | Default NOW() |

#### `ohlcv_price_series` Table (Future Ready)

This table is created in the MVP phase but remains empty, establishing schema for future price data integration.

| Field Name | Data Type | Description | Notes |
|:---|:---|:---|:---|
| `series_id` | `BIGSERIAL` | Primary Key | |
| `symbol` | `VARCHAR(50)` | Stock/Option Symbol | |
| `timestamp` | `TIMESTAMP WITH TIME ZONE` | Candle start time | Sub-daily support |
| `timeframe` | `VARCHAR(10)` | 1D, 1H, 5M, etc. | |
| `open_price` | `NUMERIC(18, 8)` | Open price | |
| `high_price` | `NUMERIC(18, 8)` | High price | |
| `low_price` | `NUMERIC(18, 8)` | Low price | |
| `close_price` | `NUMERIC(18, 8)` | Close price | |
| `volume` | `INTEGER` | Volume | |

### 4.3 Database Constraints and Indexes

#### Primary Constraints
```sql
-- Trades table
ALTER TABLE trades ADD CONSTRAINT valid_instrument_type
  CHECK (instrument_type IN ('EQUITY', 'OPTION'));
ALTER TABLE trades ADD CONSTRAINT valid_side
  CHECK (side IN ('BUY', 'SELL') OR side IS NULL);
ALTER TABLE trades ADD CONSTRAINT valid_event_type
  CHECK (event_type IN ('fill', 'cancel', 'amend'));

-- Positions table
ALTER TABLE positions ADD CONSTRAINT unique_position
  UNIQUE(symbol, instrument_type, option_details);

-- Processing log
ALTER TABLE processing_log ADD CONSTRAINT unique_processing_attempt
  UNIQUE(file_path, processing_started_at);
```

#### Performance Indexes
```sql
-- Primary performance indexes
CREATE INDEX idx_trades_exec_timestamp ON trades(exec_timestamp);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_symbol_timestamp ON trades(symbol, exec_timestamp);
CREATE INDEX idx_trades_instrument_type ON trades(instrument_type);

-- P&L calculation indexes
CREATE INDEX idx_trades_symbol_pos_effect ON trades(symbol, pos_effect, exec_timestamp);
CREATE INDEX idx_trades_open_positions ON trades(symbol, pos_effect)
  WHERE pos_effect = 'TO OPEN';

-- Audit trail indexes
CREATE INDEX idx_trades_source_file ON trades(source_file_path);
CREATE UNIQUE INDEX idx_trades_unique_key ON trades(unique_key);

-- Position tracking indexes
CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_positions_open ON positions(symbol) WHERE closed_at IS NULL;
```

-----

## 5. P&L Calculation Methodology

### 5.1 Chosen Method: Average Cost (Weighted Average)

**Rationale:** Based on trading application research, average cost provides:
- **Computational efficiency**: Faster than FIFO/LIFO lot tracking
- **Consistency**: Same results regardless of execution order
- **Platform compatibility**: Matches most trading platform calculations
- **Simplicity**: Easier to audit and debug

### 5.2 Implementation Algorithm

#### Position Opening (TO OPEN)
```python
# Update position with new shares
new_total_shares = current_qty + trade_qty
new_total_cost = total_cost + (trade_qty * trade_price)
new_avg_cost = new_total_cost / new_total_shares
```

#### Position Closing (TO CLOSE)
```python
# Calculate realized P&L
shares_sold = abs(trade_qty)
cost_basis = avg_cost_basis * shares_sold
proceeds = shares_sold * trade_price
realized_pnl = proceeds - cost_basis

# Update remaining position
remaining_shares = current_qty - shares_sold
remaining_cost = total_cost - cost_basis
# avg_cost_basis remains unchanged
```

### 5.3 Alternative Methods (Future Enhancement)

- **FIFO**: Better for long-term tax optimization
- **LIFO**: Better for active traders minimizing short-term gains
- **Specific Lot**: Manual lot selection for advanced users

-----

## 6. User Interface (MVP Reporting)

### 6.1 Dashboard (The High-Level View)

The primary dashboard must be the default view, summarizing performance over a user-selected time period.

- [ ] **Total Net P&L:** Sum of realized P&L for all closed positions
- [ ] **Win/Loss Ratio:** (Number of Profitable Trades) / (Number of Losing Trades)
- [ ] **Total Trades:** Count of all filled orders
- [ ] **Average Winning Trade Value:** Average P&L of profitable trades
- [ ] **Average Losing Trade Value:** Average P&L of losing trades
- [ ] **Max Drawdown:** Largest peak-to-trough decline in cumulative P&L
- [ ] **Account Equity Curve:** Line chart showing cumulative P&L over time
- [ ] **Top Setup Patterns:** Best and worst performing setup patterns by P&L
- [ ] **Pattern Distribution:** Breakdown of trades by setup pattern type

### 6.2 Detailed Trade Reports

- [ ] **Daily Trade Log:** Sortable, searchable table listing all completed trades for selected date range with columns: `symbol`, `opened_at`, `closed_at`, `total_qty`, `entry_avg_price`, `exit_avg_price`, `setup_pattern`, `trade_notes`, `net_pnl`
- [ ] **Execution Detail View:** Drill-down view showing individual executions that comprise each completed trade
- [ ] **Open Positions:** Current holdings with current quantity, average cost basis, and estimated unrealized P&L (when price data available)
- [ ] **Closed Positions:** Historical positions with realized P&L, hold time, and return percentages

### 6.3 Filtering and Time Selection

- [ ] **Timeframe Selector:** Dropdown for predefined periods (Today, Last Week, Last Month, YTD, Custom Range)
- [ ] **Instrument Filter:** Toggle/Dropdown for **Equity**, **Option**, or **All**
- [ ] **Platform Filter:** Toggle/Dropdown for **TOS** (future: multiple platforms)
- [ ] **Symbol Filter:** Text input for specific symbol analysis
- [ ] **Notes Search:** Text search within trade notes for finding specific thoughts or keywords
- [ ] **Setup Pattern Filter:** Filter by specific setup patterns

-----

## 7. Command Line Interface (CLI)

### 7.1 Core Commands

#### Typical Workflow

The application uses a **two-step workflow** for processing trades:

```bash
# Step 1: Ingest NDJSON file (stores executions in trades table)
trading-journal ingest file data.ndjson

# Step 2: Process completed trades (matches buys with sells, creates completed_trades records)
trading-journal db process-trades

# Step 3: View reports (completed trades now visible)
trading-journal report trades
```

**Important**: Reports show data from the `completed_trades` table. You must run both ingestion and trade processing to see trades in reports.

#### Ingestion Commands
```bash
# Single file ingestion
trading-journal ingest file data.ndjson

# Batch processing
trading-journal ingest batch *.ndjson --output-summary

# Dry run (validation only)
trading-journal ingest file data.ndjson --dry-run

# Verbose processing
trading-journal ingest file data.ndjson --verbose
```

#### Reporting Commands
```bash
# Dashboard metrics
trading-journal report dashboard --date-range "2025-01-01,2025-01-31"

# Trade log
trading-journal report trades --symbol AAPL --format json

# Trade log with notes search
trading-journal report trades --notes-search "FOMO" --date-range "2025-01-01,2025-01-31"

# Open positions
trading-journal report positions --open-only

# P&L summary
trading-journal report pnl --monthly

# Setup pattern analysis
trading-journal report patterns --date-range "2025-01-01,2025-01-31"
```

#### Pattern Management Commands
```bash
# Annotate completed trades with setup patterns
trading-journal pattern annotate --completed-trade-id 12345 --pattern "MACD Scalp"

# Bulk pattern annotation by symbol/date for completed trades
trading-journal pattern annotate --symbol AAPL --date "2025-01-15" --pattern "5min ORB"

# List all unique patterns used
trading-journal pattern list

# Setup pattern performance report
trading-journal pattern performance --pattern "MACD Scalp"
```

#### Notes Management Commands
```bash
# Add notes to a specific completed trade
trading-journal notes add --completed-trade-id 12345 --text "Felt FOMO, should have waited for better entry"

# Add notes to completed trades by criteria
trading-journal notes add --symbol AAPL --date "2025-01-15" --text "Good execution on pullback strategy"

# View trade notes
trading-journal notes show --completed-trade-id 12345

# Edit existing notes
trading-journal notes edit --completed-trade-id 12345

# Bulk notes via file import
trading-journal notes import --file notes.txt --format csv
```

#### Completed Trade Management Commands
```bash
# List completed trades
trading-journal trades list --date-range "2025-01-01,2025-01-31"

# Show trade details with all executions
trading-journal trades show --completed-trade-id 12345

# Mark executions as part of a completed trade
trading-journal trades create --execution-ids "123,124,125" --pattern "MACD Scalp" --notes "Great entry timing"
```

#### Database Management
```bash
# Schema setup
trading-journal db migrate

# Health check
trading-journal db status

# Reset (with confirmation)
trading-journal db reset --confirm

# Process completed trades from executions (match buys with sells)
trading-journal db process-trades

# Process trades for specific symbol only
trading-journal db process-trades --symbol AAPL
```

### 7.2 Configuration Options

```bash
# Database connection
trading-journal config set db-host localhost
trading-journal config set db-name trading_journal

# P&L method (future enhancement)
trading-journal config set pnl-method average_cost

# Display current configuration
trading-journal config show
```

-----

## 8. Implementation Phases

### Phase 1: Core Data Model (Weeks 1-2)
**Deliverables:**
1. Database schema creation with all tables and constraints
2. Basic NDJSON ingestion (single file processing)
3. Core trades table population with validation
4. Simple duplicate detection using unique_key
5. Unit tests for ingestion logic

### Phase 2: P&L Engine (Weeks 3-4)
**Deliverables:**
1. Position tracking table implementation
2. Average cost basis calculation engine
3. Realized P&L calculation on position close
4. Position update triggers and consistency checks
5. Comprehensive P&L calculation tests

### Phase 3: MVP Reporting (Week 5)
**Deliverables:**
1. CLI interface with all core commands
2. Core dashboard metrics implementation
3. Daily trade log report with filtering
4. Open/closed position reports
5. Integration testing for end-to-end workflows

### Phase 4: Production Features (Week 6)
**Deliverables:**
1. Batch file processing with progress tracking
2. Advanced error handling and recovery procedures
3. Performance optimization and indexing validation
4. Comprehensive testing and documentation
5. Production deployment procedures

-----

## 9. Edge Cases & Error Handling

### 9.1 Edge Cases to Handle

1. **Duplicate Imports:** Handled by `unique_key` and **UPSERT** logic (F.1.3)
2. **Malformed NDJSON Records:** Skip record, log error with file/line details, continue processing
3. **Missing Time Fields:** Records without timestamps flagged with issue, placed at end of chronological reports
4. **Options without Expiration/Strike:** Flagged as issue, treated as Equity if possible, tracked for review
5. **Amendment Records:** Update existing orders appropriately, maintain audit trail
6. **Multi-leg Spreads:** Preserve spread context, handle as related individual legs

### 9.2 Error Recovery Workflows

#### File Processing Errors
- **Schema Validation Failures:** Log specific field errors, continue with valid records
- **Database Connection Loss:** Retry with exponential backoff, transaction rollback on failure
- **Partial File Failures:** Option to continue or rollback entire file, user configurable
- **Duplicate File Processing:** Detect and skip, log warning with processing history

#### Data Consistency Errors
- **Position Calculation Mismatches:** Log discrepancies, flag for manual review
- **P&L Calculation Errors:** Detailed error logging with trade sequence for debugging
- **Constraint Violations:** Graceful handling with user-friendly error messages

-----

## 10. Configuration Management

### 10.1 Configuration Structure
```python
# Environment Variables
DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'trading_journal'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD'),
}

LOGGING_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'file': os.getenv('LOG_FILE', 'trading_journal.log'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
}

APPLICATION_CONFIG = {
    'pnl_method': os.getenv('PNL_METHOD', 'average_cost'),
    'timezone': os.getenv('TIMEZONE', 'US/Eastern'),
    'batch_size': int(os.getenv('BATCH_SIZE', '1000')),
    'max_retries': int(os.getenv('MAX_RETRIES', '3')),
}
```

### 10.2 Configuration Files
- **development.env**: Local development settings
- **production.env**: Production environment configuration
- **test.env**: Testing environment with isolated database

-----

## 11. Success Metrics

### 11.1 Performance Benchmarks
- [ ] **10,000 records ingestion in < 5 seconds** (primary requirement)
- [ ] **Dashboard query response time < 500ms** for 1-year data
- [ ] **Memory usage < 500MB** for batch processing 1000+ files
- [ ] **Database size growth rate** < 10MB per 1000 trades

### 11.2 Data Quality Metrics
- [ ] **99.9% data ingestion accuracy** validated against source files
- [ ] **Zero P&L calculation discrepancies** on closed positions
- [ ] **100% audit trail completeness** (ability to recreate calculations)
- [ ] **Zero data loss** upon ingestion (all raw data preserved)

### 11.3 Operational Metrics
- [ ] **Recovery time < 30 seconds** from database connection failures
- [ ] **Zero manual intervention** required for routine file processing
- [ ] **Error detection rate > 99%** for malformed input files
- [ ] **100% TDD test coverage** for core business logic

-----

## 12. Technology Stack

### 12.1 Core Technologies
- **Database**: PostgreSQL 14+ (JSONB support, excellent performance)
- **Language**: Python 3.11+ (matches existing converter)
- **CLI Framework**: Click (consistent with converter)
- **Web Framework**: Flask (production version for browser-based interface)
- **Database ORM**: SQLAlchemy 2.0 (type safety, async support)
- **Migration Tool**: Alembic (integrated with SQLAlchemy)

### 12.2 Development Tools
- **Testing**: pytest (TDD requirement)
- **Type Checking**: mypy for type safety
- **Code Formatting**: black, isort for consistency
- **Dependency Management**: uv (consistent with converter)
- **Documentation**: Sphinx for API docs

### 12.3 Development Environment
- **Python Version**: 3.11+ (using .python-version file)
- **Virtual Environment**: uv managed
- **Database**: PostgreSQL with local development instance
- **IDE**: Compatible with VS Code, PyCharm

-----

## 13. Future Enhancements

### 13.1 Phase 2 Features (Post-MVP)

#### Web User Interface (Flask-based)
1. **Browser-based Dashboard**: Replace CLI reports with interactive web dashboard
2. **Setup Pattern Management**: Web interface for managing predefined setup patterns with dropdown selection
3. **Interactive Charts**: Charting component integration for trade visualization
4. **Responsive Design**: Mobile-friendly interface for portfolio monitoring

#### Advanced P&L Methods
1. **FIFO/LIFO Calculation Options**: Allow users to choose tax-optimized P&L methods
2. **Specific Lot Identification**: Manual lot selection for advanced users
3. **Tax Loss Harvesting**: Automated identification of tax optimization opportunities

#### Enhanced Pattern Analysis
1. **Pattern Performance Analytics**: Deep-dive analysis by setup pattern with win/loss ratios
2. **Pattern Correlation Analysis**: Identify which patterns work best in different market conditions
3. **Setup Optimization**: Recommend best-performing patterns based on historical data

#### Trading Psychology & Notes Analysis
1. **Emotional Pattern Recognition**: Analyze trade notes to identify emotional patterns affecting performance
2. **Keyword Analytics**: Track performance correlation with specific emotions/thoughts in notes (FOMO, confidence, etc.)
3. **Trading Journal Insights**: Generate insights from notes to improve decision-making
4. **Notes Export**: Export annotated trades for external analysis or sharing with mentors

#### Multiple Platform Support
1. **NinjaTrader Integration**: Extend ingestion to support futures trading data
2. **Interactive Brokers**: Support for additional broker export formats
3. **Manual Trade Entry**: Web interface for manual trade input

#### Advanced Analytics
1. **Risk Metrics**: Sharpe ratio, maximum drawdown, volatility analysis
2. **Calendar Analysis**: Performance by day of week, time of day patterns
3. **Market Condition Analysis**: Performance correlation with market volatility/trends

### 13.2 Phase 3 Features (Advanced)

#### Real-time Integration
1. **Live Data Feeds**: Integration with price data providers for real-time unrealized P&L
2. **Position Monitoring**: Alerts for position changes, stop loss triggers
3. **API Development**: REST API for third-party integrations

#### Advanced Visualization
1. **Granular Charting**: Integration with TradingView or similar for trade visualization on price charts
2. **Performance Dashboards**: Advanced web-based dashboards with interactive charts
3. **Mobile Interface**: Mobile app for portfolio monitoring

#### Enterprise Features
1. **Multi-user Support**: User authentication and role-based access
2. **Portfolio Management**: Multiple portfolio/account management
3. **Compliance Reporting**: Automated regulatory reporting features

-----

## 14. Acceptance Criteria

### 14.1 MVP Completion Criteria

#### Core Functionality
- [ ] Successfully ingests 100% of provided NDJSON test files without data loss
- [ ] Calculates accurate P&L using average cost basis for all test scenarios
- [ ] Generates correct dashboard metrics for 1-year historical data
- [ ] Processes 10,000 records in under 5 seconds on target hardware

#### User Experience
- [ ] CLI provides clear, helpful error messages for all failure scenarios
- [ ] Reports are readable, accurate, and properly formatted
- [ ] Dry-run mode works correctly without database modifications
- [ ] All filtering options work as specified

#### Technical Requirements
- [ ] 100% test coverage for P&L calculation logic
- [ ] Database schema supports all required queries efficiently
- [ ] Error handling gracefully manages all identified edge cases
- [ ] Configuration system works in development, test, and production environments

### 14.2 Production Readiness Criteria

#### Performance & Scalability
- [ ] Meets all performance benchmarks under load testing
- [ ] Memory usage remains stable during extended batch processing
- [ ] Database queries remain fast with 1+ million trade records
- [ ] Error recovery procedures tested and documented

#### Operational Requirements
- [ ] Comprehensive logging for production monitoring
- [ ] Database backup and recovery procedures tested
- [ ] Migration scripts work correctly in production environment
- [ ] Documentation complete for operators and users

-----

This unified PRD serves as the definitive specification for the Trading Journal MVP. All implementation work should reference this document as the single source of truth for requirements, technical specifications, and success criteria.