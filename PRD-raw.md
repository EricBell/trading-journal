This is the draft of the Product Requirements Document (PRD) for the **Trading Journal** project, incorporating all the requirements and details you have provided, and following the structure of your example PRD.

# Product Requirements Document (PRD)

# 📈 Trading Journal: Data Ingestion and Core Storage

**Version:** 1.0 (MVP Draft)
**Last Updated:** 2025-11-26
**Status:**

  - 📝 **DRAFT** - Core requirements being defined and prioritized
  - ⏳ **PHASE 1 (TDD)** - Data model and ingestion logic

**Implementation Summary (Target):**

**Version 1.0 (Core Data Model & MVP Reporting):**

  - 🎯 Functional Requirements: 100% target
  - 🎯 Non-Functional Requirements: 100% target
  - 🎯 Success Metrics: 100% target
  - 🎯 Reporting: Core dashboard metrics and daily trade log implemented

-----

## 1\. Overview

### Problem Statement

Day traders require a dedicated, centralized application to analyze their performance across multiple trading platforms. While the existing **Schwab CSV to JSON Converter** successfully processes raw data, traders still lack an integrated, relational application to:

1.  **Persist and Centralize** NDJSON trade data into a single, query-optimized PostgreSQL database.
2.  **Normalize and Relate** orders and executions across different instrument types (Equities and Options).
3.  Provide immediate **analytical value** through essential performance metrics (P\&L, Win/Loss Ratio) via an MVP dashboard.

Manual aggregation limits analytical depth and makes crucial performance analysis difficult and time-consuming.

### Goal

Create a **PostgreSQL-based backend data ingestion service** that consumes standardized NDJSON trade files (initially from ThinkOrSwim) and an **MVP Reporting Interface** to display core performance metrics. The architecture must be robust, extensible, and designed to integrate future granular historical price data.

### Non-Goals

  - **Not a Data Converter:** Does not handle the conversion of raw CSV files; it strictly consumes pre-converted NDJSON.
  - **Not a Live Trading Tool:** Does not connect to live or historical platform APIs (e.g., ThinkOrSwim, NinjaTrader). All data is based on file imports.
  - **Not a Charting Application (in MVP):** Does not include complex visualization using charting packages (e.g., TradingView). This is a **Future Enhancement (Section 8)**.

-----

## 2\. Background & Context

### Current Situation

Traders manually run the CSV-to-JSON converter, resulting in clean NDJSON files for each day/account. They currently trade **Equities and Options** almost daily. These files are ready for ingestion but lack a unified, relational storage mechanism required for cross-trade and long-term analysis.

### Data Ingestion Source

The primary input is **NDJSON files** created by the previous converter project. These files contain records with normalized fields (e.g., `exec_time`, `symbol`, `qty`, `price`).

### Technical Environment

  - **Database**: PostgreSQL (available and preferred).
  - **Input Format**: NDJSON (Newline Delimited JSON).
  - **Development Approach**: TDD (Test-Driven Development) with a commitment to comprehensive unit testing.

### Use Cases

1.  **Historical Data Archive**: Persist all trade history in a searchable, relational format.
2.  **Daily Performance Review**: Quickly review the day's performance via key metrics like Net P\&L and Win/Loss Ratio upon data ingestion.
3.  **Future Granularity Integration**: The data model must support linking trade executions to high-granularity (sub-daily) OHLCV data when it becomes available.

-----

## 3\. Requirements

### 3.1 Functional Requirements

#### F.1 Ingestion and File Handling

  - [ ] **F.1.1** The service must read one or more **NDJSON files** containing trade records.
  - [ ] **F.1.2** Must validate the schema of each NDJSON record against the expected output schema (Section 4).
  - [ ] **F.1.3** Must perform **UPSERT** logic based on a unique trade identifier to prevent duplicate records upon re-import.

#### F.2 Data Modeling and Persistence

  - [ ] **F.2.1** Trades must be stored relationally in PostgreSQL, with a schema optimized for both Equities and Options.
  - [ ] **F.2.2** Must convert all temporal fields (e.g., `exec_time`) from the input format (e.g., "10/24/25 09:51:38") into the **ISO-8601 standard** for PostgreSQL storage.
  - [ ] **F.2.3** Must automatically determine and persist the instrument type for each record (**EQUITY, OPTION**) based on the presence of fields like `Exp` and `Strike`.
  - [ ] **F.2.4** Must calculate and persist the P\&L for closed trades during the ingestion process or via a defined database view/function.

#### F.3 MVP Reporting and Filtering

  - [ ] **F.3.1** Implement the Core Dashboard metrics (Section 5.1).
  - [ ] **F.3.2** Implement the Daily Trade Log report (Section 5.2).
  - [ ] **F.3.3** Implement basic filtering based on **Timeframe**, **Platform**, and **Instrument Type**.

### 3.2 Non-Functional Requirements

#### N.1 Performance

  - [ ] **N.1.1** The ingestion service must process and persist **10,000 trade records in under 5 seconds**.
  - [ ] **N.1.2** Database schema must be optimized (e.g., proper indexing) for fast read access for daily/weekly reporting queries.

#### N.2 Usability (Ingestion Tool)

  - [ ] **N.2.1** The service must be executable via a simple **Command-Line Interface (CLI)**.
  - [ ] **N.2.2** Provide clear, progress-based output during ingestion (e.g., "Processing file X of Y... 100 records inserted/updated").

#### N.3 Reliability and Error Handling

  - [ ] **N.3.1** Must use **database transactions** to ensure that entire file imports succeed or fail atomically.
  - [ ] **N.3.2** Log all schema validation errors and database failures, reporting the specific line number and file name.

#### N.4 Maintainability and Development

  - [ ] **N.4.1** **Test-Driven Development (TDD):** All implementation work must follow TDD methodology.
  - [ ] **N.4.2** **Unit Testing:** All core components (ingestion logic, data normalization, P\&L calculation) must be covered by comprehensive unit tests.
  - [ ] **N.4.3** **Project Phasing:** The PRD must support digestion by an external LLM (e.g., Claude) to generate a phased task list for iterative project build-out.

-----

## 4\. Data Schema

### 4.1 Input Schema (Based on Converter Output)

The input is NDJSON. Each line represents a single trade execution or order update and conforms to the following conceptual schema:

```json
{
  "section": "string",       // Section name (e.g., "Filled Orders")
  "row_index": "integer",    // Line number in CSV
  "exec_time": "string|null", // Execution timestamp (e.g., "10/24/25 09:51:38")
  "side": "string|null",     // BUY or SELL
  "qty": "integer|null",     // Quantity (signed)
  "pos_effect": "string|null", // Position effect (TO OPEN, TO CLOSE)
  "symbol": "string|null",   // Symbol (required)
  "price": "float|null",     // Price
  "net_price": "float|null", // Net price
  "price_improvement": "float|null",
  "order_type": "string|null",
  "Exp": "string|null",      // OPTION ONLY: Expiration date
  "Strike": "float|null",    // OPTION ONLY: Strike price
  "Type": "string|null",     // OPTION ONLY: CALL or PUT
  "raw": "string",           // Original CSV row
  "issues": ["string"]       // Array of issue codes
}
```

### 4.2 Output Database Schema (PostgreSQL)

#### `trades` Table (Core Execution Data)

| Field Name | Data Type (PostgreSQL) | Description | Notes |
| :--- | :--- | :--- | :--- |
| `trade_id` | `BIGSERIAL` | Primary Key. | |
| `unique_key` | `TEXT` | Unique hash (e.g., of `raw` + `source_file` + `row_index`). **Used for UPSERT logic.** | |
| `instrument_type` | `VARCHAR(10)` | **EQUITY** or **OPTION**. | Used for filtering. |
| `platform_source` | `VARCHAR(20)` | **TOS** (ThinkOrSwim) or FUTURE. | |
| `exec_timestamp` | **`TIMESTAMP WITH TIME ZONE`** | Normalized ISO-8601 execution time. | **F.2.2** |
| `symbol` | `VARCHAR(50)` | Stock/Option Symbol. | |
| `side` | `VARCHAR(10)` | BUY or SELL. | |
| `qty` | `INTEGER` | Quantity (signed). | |
| `price` | `NUMERIC(18, 8)` | Execution Price. | |
| `net_price` | `NUMERIC(18, 8)` | Net Price/Proceeds. | Used for P\&L calculation. |
| `pos_effect` | `VARCHAR(10)` | TO OPEN or TO CLOSE. | |
| `exp_date` | `DATE` | Option Expiration Date. | NULL for Equities. |
| `strike_price` | `NUMERIC(18, 4)` | Option Strike Price. | NULL for Equities. |
| `option_type` | `VARCHAR(4)` | CALL or PUT. | NULL for Equities. |
| `raw_data` | `TEXT` | The entire original CSV row (`raw` field). | Preserves data integrity. |

#### `ohlcv_price_series` Table (Future Ready)

This table must be created in the MVP phase, even if empty, to establish the schema for future, high-granularity data ingestion.

| Field Name | Data Type (PostgreSQL) | Description | Notes |
| :--- | :--- | :--- | :--- |
| `series_id` | `BIGSERIAL` | Primary Key. | |
| `symbol` | `VARCHAR(50)` | Stock/Option Symbol. | |
| `timestamp` | **`TIMESTAMP WITH TIME ZONE`** | Start time of the candle. | Must support sub-daily granularity. |
| `timeframe` | `VARCHAR(10)` | e.g., 1D, 1H, 5M. | |
| `open_price` | `NUMERIC(18, 8)` | | |
| `high_price` | `NUMERIC(18, 8)` | | |
| `low_price` | `NUMERIC(18, 8)` | | |
| `close_price` | `NUMERIC(18, 8)` | | |
| `volume` | `INTEGER` | | |

-----

## 5\. User Interface (MVP Reporting)

The MVP interface focuses on essential textual reports and an on-screen dashboard.

### 5.1 Dashboard (The High-Level View)

The primary dashboard must be the default view, summarizing performance over a user-selected time period.

  - [ ] **Total Net P\&L:** Sum of calculated P\&L for all closed trades.
  - [ ] **Win/Loss Ratio:** (Number of Profitable Trades) / (Number of Losing Trades).
  - [ ] **Account Equity Curve:** A line chart showing cumulative P\&L over time.
  - [ ] **Max Drawdown:** The largest peak-to-trough decline in cumulative P\&L.
  - [ ] **Average Winning/Losing Trade Value.**

### 5.2 Detailed Trade Reports

  - [ ] **Daily Trade Log:** A sortable and searchable table listing all executions for a selected day, including `symbol`, `exec_timestamp`, `side`, `qty`, `price`, and calculated P\&L.
  - [ ] **Open Positions:** A filtered view of all `TO OPEN` records that lack a corresponding `TO CLOSE` trade.

### 5.3 Filtering and Time Selection

  - [ ] **Timeframe Selector:** Dropdown for predefined periods (Today, Last Week, Last Month, etc.) and custom date range selector.
  - [ ] **Instrument Filter:** Toggle/Dropdown for **Equity** or **Option**.
  - [ ] **Platform Filter:** Toggle/Dropdown for **TOS** (and future platforms).

-----

## 6\. Edge Cases & Error Handling

### Edge Cases to Handle

1.  **Duplicate Imports:** Handled by `unique_key` and **UPSERT** logic (F.1.3).
2.  **Malformed NDJSON Records:** Must skip the record, log the error (N.3.2), and continue ingestion.
3.  **Missing Time Fields:** Records without a time field must be flagged with an issue and placed at the end of the reported trade list.
4.  **Options without Expiration/Strike:** Flagged as an issue; treated as an Equity for storage purposes if possible, but tracked for review.

-----

## 7\. Success Metrics

### How do we measure success?

  - [ ] **100% Data Integrity:** Zero data loss upon ingestion (all raw data preserved in `raw_data` field).
  - [ ] **Performance Target:** Ingestion meets the 10,000 records in \< 5 seconds standard (N.1.1).
  - [ ] **Relational Accuracy:** Correct calculation and display of **Total Net P\&L** across multiple days and instrument types.
  - [ ] **Development Quality:** All core features pass the **TDD** unit test suite.

-----

## 8\. Future Enhancements

### Potential Future Features (Phase 2 and Beyond)

1.  **NinjaTrader Integration:** Implement ingestion logic and schema changes to handle **Futures** trade data from NinjaTrader exports.
2.  **Granular Charting Visualization:** Utilize the `ohlcv_price_series` table and integrate with a charting package (e.g., TradingView) to visualize trade entries, stops, and exits on high-granularity candles.
3.  **Advanced Reporting:** Summary statistics grouped by time of day, day of week, or trading strategy.
4.  **Configuration Interface:** A simple screen for managing database connection settings and import/archive directories.