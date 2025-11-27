# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Trading Journal** application designed to ingest and analyze trading data from brokerage platforms. The project is currently in **Phase 1 (TDD)** and follows a comprehensive PRD located in `PRD.md`.

### Architecture Philosophy

**Three-Tier Data Hierarchy:**
1. **EXECUTIONS** (`trades` table) - Individual broker fills/partial fills from NDJSON input
2. **TRADES** (`completed_trades` table) - Complete round-trip business transactions (entry + exit)
3. **POSITIONS** (`positions` table) - Running totals and average cost basis per symbol

**Key Relationships:**
- Multiple executions → One completed trade
- Multiple completed trades → One position (per symbol)
- Setup patterns and notes belong at the **TRADE** level, not execution level

## Development Commands

### Project Setup
```bash
# Install dependencies with uv
uv install

# Run the minimal application
python main.py
```

### Future Development Commands (from PRD)
```bash
# Database operations (when implemented)
trading-journal db migrate
trading-journal db status
trading-journal db reset --confirm

# Data ingestion (when implemented)
trading-journal ingest data.ndjson
trading-journal ingest --batch *.ndjson --dry-run

# Reporting (when implemented)
trading-journal report dashboard --date-range "2025-01-01,2025-01-31"
trading-journal report trades --symbol AAPL
trading-journal pattern annotate --completed-trade-id 123 --pattern "MACD Scalp"
trading-journal notes add --completed-trade-id 123 --text "Great entry timing"
```

## Technical Stack

- **Language**: Python 3.11+ (requires >= 3.14 per pyproject.toml)
- **Database**: PostgreSQL 14+ with JSONB support
- **ORM**: SQLAlchemy 2.0 with Alembic migrations
- **CLI**: Click framework
- **Web Framework**: Flask (production version)
- **Testing**: pytest (TDD approach)
- **Dependency Management**: uv
- **Code Quality**: black, isort, mypy

## Data Input Format

The application consumes NDJSON files from an existing **Schwab CSV to JSON Converter** project located at `../schwab-csv-to-json`. Sample data structure:

```json
{
  "exec_time": "2025-11-04T10:17:00",
  "side": "BUY", "qty": 300, "pos_effect": "TO OPEN",
  "symbol": "RANI", "net_price": 2.489,
  "event_type": "fill", "asset_type": "STOCK",
  "source_file": "2025-11-04-TradeActivity.csv"
}
```

## Database Schema Considerations

### Critical Tables (from PRD)
1. **`trades`** - Individual executions with `completed_trade_id` FK
2. **`completed_trades`** - Round-trip trades with `setup_pattern` and `trade_notes`
3. **`positions`** - Current holdings with average cost basis
4. **`setup_patterns`** - Managed dropdown patterns (production version)
5. **`processing_log`** - File processing audit trail

### P&L Methodology
Uses **Average Cost (Weighted Average)** method for position tracking and P&L calculations, chosen for computational efficiency and platform compatibility.

## Implementation Phases

**Current Status: Phase 1 - Core Data Model (Weeks 1-2)**
- Database schema creation and migrations
- Basic NDJSON ingestion (single file processing)
- Duplicate detection using unique_key
- TDD approach with comprehensive unit tests

**Next Phases:**
- Phase 2: P&L Engine (Weeks 3-4)
- Phase 3: MVP Reporting (Week 5)
- Phase 4: Production Features (Week 6)

## Key Development Guidelines

- **Test-Driven Development (TDD)**: All implementation must follow TDD methodology
- **Performance Target**: 10,000 records ingestion in < 5 seconds
- **Data Integrity**: Zero P&L calculation discrepancies on closed positions
- **Annotations**: Setup patterns and notes apply to completed trades, not individual executions
- **Error Handling**: Comprehensive transaction-based error recovery with rollback capabilities

## Related Projects

The application depends on output from the **Schwab CSV to JSON Converter** located at `../schwab-csv-to-json` for NDJSON input data.