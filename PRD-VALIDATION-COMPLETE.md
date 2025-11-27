# PRD Validation and Enhancement Report

## Executive Summary

Your PRD is **well-structured** and covers the essential requirements. After analyzing the existing Schwab CSV converter and researching trading application best practices, I've identified several critical gaps and enhancements that will strengthen your implementation.

## Key Findings from Converter Analysis

### Actual NDJSON Schema (vs. Your PRD Schema)

**What the converter actually produces:**
```json
{
  "section": "Filled Orders",
  "row_index": 11,
  "exec_time": "2025-10-21T15:59:39",
  "side": "BUY",
  "qty": 3,
  "pos_effect": "TO OPEN",
  "symbol": "SPY",
  "exp": "2025-10-21",           // ISO date, not string
  "strike": 673.0,              // float, not string
  "type": "CALL",               // PUT/CALL for options
  "spread": "SINGLE",           // SINGLE, STOCK, etc.
  "price": null,                // limit price
  "net_price": 2.489,           // actual execution price
  "price_improvement": 0.3,
  "order_type": "MKT",
  "event_type": "fill",         // fill/cancel/amend
  "asset_type": "OPTION",       // OPTION/STOCK
  "option": {                   // nested option details
    "exp_date": "2025-10-21",
    "strike": 673.0,
    "right": "CALL"
  },
  "source_file": "file.csv",   // batch processing
  "source_file_index": 0,      // batch index
  "raw": "original CSV row",
  "issues": []                  // validation issues
}
```

### Critical Schema Differences from Your PRD

1. **Time fields are already ISO-8601 formatted** - no conversion needed
2. **Additional fields**: `spread`, `event_type`, `asset_type`, `option` nested object
3. **Source tracking fields**: `source_file`, `source_file_index` for batch processing
4. **Options handling**: Separate nested `option` object plus top-level `exp`, `strike`, `type`

## Major PRD Gaps Identified

### 1. Database Schema Issues

#### Missing Critical Fields
- **`event_type`**: Essential for distinguishing fills, cancels, amendments
- **`spread`**: Trading strategy context (SINGLE, VERTICAL, etc.)
- **`source_file`**: Critical for audit trail and re-processing
- **`option` nested data**: Should be stored as JSONB in PostgreSQL
- **Account/Portfolio ID**: No way to separate multiple accounts

#### Data Type Corrections
```sql
-- Your PRD had these as incorrect types:
exec_timestamp TIMESTAMP WITH TIME ZONE  -- ✓ Correct
exp_date DATE                            -- ✓ Correct
strike_price NUMERIC(18, 4)              -- ✓ Correct
option_data JSONB                        -- ✗ Missing from PRD
event_type VARCHAR(10)                   -- ✗ Missing from PRD
spread_type VARCHAR(20)                  -- ✗ Missing from PRD
source_file_path TEXT                    -- ✗ Missing from PRD
```

### 2. P&L Calculation - Critical Missing Details

Your PRD lacks specifics on **how** P&L is calculated. Research shows this is complex:

#### Recommended Approach: **Average Cost (Weighted Average)**
- **Pros**: Computationally efficient, consistent results, matches most trading platforms
- **Cons**: May not optimize for taxes (but that's not your MVP goal)
- **Implementation**: `(Total Cost of Shares) / (Total Shares)` on position close

#### Alternative Methods (Future Enhancement)
- **FIFO**: Better for long-term tax optimization
- **LIFO**: Better for active traders minimizing short-term gains
- **Specific Lot**: Manual lot selection (advanced feature)

#### Database Impact
```sql
-- Position tracking table (missing from PRD)
CREATE TABLE positions (
    position_id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    instrument_type VARCHAR(10) NOT NULL,
    current_qty INTEGER DEFAULT 0,
    avg_cost_basis NUMERIC(18, 8),
    total_cost NUMERIC(18, 8),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 3. Database Indexing Strategy

Your PRD mentions "proper indexing" but lacks specifics. For 10k+ records in <5s:

```sql
-- Primary performance indexes
CREATE INDEX idx_trades_exec_timestamp ON trades(exec_timestamp);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_symbol_timestamp ON trades(symbol, exec_timestamp);
CREATE INDEX idx_trades_instrument_type ON trades(instrument_type);

-- P&L calculation indexes
CREATE INDEX idx_trades_symbol_pos_effect ON trades(symbol, pos_effect, exec_timestamp);
CREATE INDEX idx_trades_open_positions ON trades(symbol, pos_effect) WHERE pos_effect = 'TO OPEN';

-- Audit trail indexes
CREATE INDEX idx_trades_source_file ON trades(source_file_path);
CREATE INDEX idx_trades_unique_key ON trades(unique_key) UNIQUE;
```

### 4. CLI Interface Design (Missing)

Your PRD lacks CLI specifics. Based on converter patterns:

```bash
# Basic ingestion
trading-journal ingest data.ndjson

# Batch processing
trading-journal ingest --batch *.ndjson --output-summary

# Reporting
trading-journal report dashboard --date-range "2025-01-01,2025-01-31"
trading-journal report trades --symbol AAPL --format json

# Database management
trading-journal db migrate
trading-journal db reset --confirm
```

### 5. Error Handling Workflows (Incomplete)

#### File Processing Errors
- **Schema Validation**: Detailed field-level validation rules
- **Duplicate Detection**: Enhanced UPSERT logic with conflict resolution
- **Partial File Failures**: Transaction rollback vs. partial import options
- **Recovery**: Re-processing failed files without affecting good data

#### Database Errors
- **Connection Failures**: Retry logic with exponential backoff
- **Constraint Violations**: Graceful handling and user feedback
- **Migration Failures**: Rollback procedures and manual recovery steps

### 6. Configuration Management (Missing)

```python
# config.py structure needed
DATABASE_CONFIG = {
    'host': env.get('DB_HOST', 'localhost'),
    'database': env.get('DB_NAME', 'trading_journal'),
    'user': env.get('DB_USER', 'postgres'),
    'password': env.get('DB_PASSWORD'),
}

LOGGING_CONFIG = {
    'level': env.get('LOG_LEVEL', 'INFO'),
    'file': env.get('LOG_FILE', 'trading_journal.log'),
}

P_AND_L_CONFIG = {
    'method': env.get('PNL_METHOD', 'average_cost'),  # average_cost, fifo, lifo
    'timezone': env.get('TIMEZONE', 'US/Eastern'),
}
```

## Edge Cases Discovered

### 1. Data Quality Issues
- **Missing timestamps**: Some records lack `exec_time`
- **Amendment records**: Special records that modify existing orders
- **Section headers**: Records marked with `section_header` issue
- **Multi-leg spreads**: Single order executing as multiple records

### 2. Options Complexities
- **Expiration date parsing**: Multiple formats in CSV (`21 OCT 25`, `2025-10-21`)
- **Symbol handling**: Base symbol + option chain details in separate fields
- **Spread types**: `SINGLE`, `VERTICAL`, `IRON CONDOR`, etc.

### 3. Batch Processing
- **File ordering**: Need deterministic processing order for reproducible results
- **Cross-file position tracking**: Positions may span multiple daily files
- **Memory usage**: Large batches may require streaming processing

## Enhanced Requirements

### Functional Requirements (Additions)

#### F.4 Position Tracking & P&L Calculation
- [ ] **F.4.1** Maintain real-time position balances per symbol using average cost basis
- [ ] **F.4.2** Calculate realized P&L on position close (TO CLOSE transactions)
- [ ] **F.4.3** Calculate unrealized P&L for open positions (requires future price data integration)
- [ ] **F.4.4** Handle partial position closes with proper cost basis allocation

#### F.5 Advanced Data Handling
- [ ] **F.5.1** Process amendment records to update existing trade entries
- [ ] **F.5.2** Handle multi-leg option spread orders as single strategy units
- [ ] **F.5.3** Support multiple account/portfolio separation
- [ ] **F.5.4** Maintain audit trail with file processing history

### Non-Functional Requirements (Enhanced)

#### N.5 Data Integrity & Consistency
- [ ] **N.5.1** Implement database constraints ensuring position balances are mathematically consistent
- [ ] **N.5.2** Provide data reconciliation reports comparing file data to database totals
- [ ] **N.5.3** Support "dry-run" mode for testing imports without database changes

#### N.6 Monitoring & Observability
- [ ] **N.6.1** Log detailed performance metrics: records/second, memory usage, SQL query times
- [ ] **N.6.2** Implement health checks for database connectivity and schema version
- [ ] **N.6.3** Provide import summary reports with error counts and processing statistics

## Database Schema Enhancements

### Updated `trades` Table
```sql
CREATE TABLE trades (
    trade_id BIGSERIAL PRIMARY KEY,
    unique_key TEXT UNIQUE NOT NULL,

    -- Execution details
    exec_timestamp TIMESTAMP WITH TIME ZONE,
    event_type VARCHAR(10) NOT NULL, -- fill, cancel, amend

    -- Instrument details
    symbol VARCHAR(50) NOT NULL,
    instrument_type VARCHAR(10) NOT NULL, -- EQUITY, OPTION

    -- Trade details
    side VARCHAR(10), -- BUY, SELL
    qty INTEGER,
    pos_effect VARCHAR(10), -- TO OPEN, TO CLOSE

    -- Pricing
    price NUMERIC(18, 8), -- limit price
    net_price NUMERIC(18, 8), -- execution price
    price_improvement NUMERIC(18, 8),

    -- Options (nullable for equities)
    exp_date DATE,
    strike_price NUMERIC(18, 4),
    option_type VARCHAR(4), -- CALL, PUT
    spread_type VARCHAR(20), -- SINGLE, VERTICAL, etc.
    option_data JSONB, -- full option details

    -- Processing metadata
    platform_source VARCHAR(20) DEFAULT 'TOS',
    source_file_path TEXT,
    source_file_index INTEGER,
    raw_data TEXT NOT NULL,
    processing_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Position tracking
    realized_pnl NUMERIC(18, 8), -- calculated on close

    -- Indexes for performance
    CONSTRAINT valid_instrument_type CHECK (instrument_type IN ('EQUITY', 'OPTION')),
    CONSTRAINT valid_side CHECK (side IN ('BUY', 'SELL') OR side IS NULL),
    CONSTRAINT valid_event_type CHECK (event_type IN ('fill', 'cancel', 'amend'))
);
```

### New `positions` Table (Missing from PRD)
```sql
CREATE TABLE positions (
    position_id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    instrument_type VARCHAR(10) NOT NULL,
    option_details JSONB, -- for option positions

    -- Position state
    current_qty INTEGER DEFAULT 0,
    avg_cost_basis NUMERIC(18, 8),
    total_cost NUMERIC(18, 8),

    -- Timestamps
    opened_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE,

    -- P&L tracking
    realized_pnl NUMERIC(18, 8) DEFAULT 0,

    UNIQUE(symbol, instrument_type, option_details)
);
```

### New `processing_log` Table (Missing from PRD)
```sql
CREATE TABLE processing_log (
    log_id BIGSERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    processing_started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    records_processed INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'processing', -- processing, completed, failed
    error_message TEXT,

    UNIQUE(file_path, processing_started_at)
);
```

## Implementation Phases (Revised)

### Phase 1: Core Data Model (Weeks 1-2)
1. **Database setup and migrations**
2. **Basic NDJSON ingestion** (single file)
3. **Core trade table population**
4. **Simple duplicate detection**

### Phase 2: P&L Engine (Weeks 3-4)
1. **Position tracking implementation**
2. **Average cost basis calculation**
3. **Realized P&L on position close**
4. **Basic validation and error handling**

### Phase 3: MVP Reporting (Week 5)
1. **CLI interface implementation**
2. **Core dashboard metrics**
3. **Daily trade log report**
4. **Basic filtering by date, symbol, instrument type**

### Phase 4: Production Features (Week 6)
1. **Batch file processing**
2. **Advanced error handling and recovery**
3. **Performance optimization and indexing**
4. **Comprehensive testing and documentation**

## Recommended Technology Stack

### Core Technologies
- **Database**: PostgreSQL 14+ (JSONB support, excellent performance)
- **Language**: Python 3.11+ (matches existing converter)
- **CLI Framework**: Click (consistent with converter)
- **Database ORM**: SQLAlchemy 2.0 (type safety, async support)
- **Migration Tool**: Alembic (integrated with SQLAlchemy)

### Development Tools
- **Testing**: pytest (TDD requirement)
- **Type Checking**: mypy
- **Code Formatting**: black, isort
- **Dependency Management**: uv (consistent with converter)

## Success Metrics (Enhanced)

### Performance Benchmarks
- [ ] **10,000 records ingestion in < 5 seconds** (your existing goal)
- [ ] **Dashboard query response time < 500ms** for 1-year data
- [ ] **Memory usage < 500MB** for batch processing 1000+ files
- [ ] **Database size growth rate** < 10MB per 1000 trades

### Data Quality Metrics
- [ ] **99.9% data ingestion accuracy** (validated against source files)
- [ ] **Zero P&L calculation discrepancies** on closed positions
- [ ] **100% audit trail completeness** (ability to recreate any calculation)

### Operational Metrics
- [ ] **Recovery time < 30 seconds** from database connection failures
- [ ] **Zero manual intervention** required for routine file processing
- [ ] **Error detection rate > 99%** for malformed input files

## Next Steps

1. **Review and approve** these enhancements to your PRD
2. **Set up development environment** with recommended tech stack
3. **Create detailed database schema** with all tables and constraints
4. **Implement Phase 1** with TDD approach
5. **Establish CI/CD pipeline** for automated testing

Your original PRD provides a solid foundation. These enhancements address the real-world complexities of trading data and position the project for successful implementation and future scalability.