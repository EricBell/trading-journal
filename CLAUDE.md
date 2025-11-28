# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Trading Journal** application designed to ingest and analyze trading data from brokerage platforms. The project has **completed Phase 3 (MVP)** and is now in **Phase 4 (Production Features)**. See `PRD.md` for complete specifications.

**Bonus Features Implemented:**
- Multi-user support with user authentication
- API key authentication system
- Admin mode for development/testing
- Comprehensive dashboard analytics

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
uv sync

# Run migrations
uv run python main.py db migrate

# Create first user (requires admin mode)
export ADMIN_MODE_ENABLED=true
export ADMIN_MODE_USER_ID=1
uv run python create_user.py

# Set API key for subsequent commands
export TRADING_JOURNAL_API_KEY=your_api_key_here
```

### Development Commands

#### Typical Workflow (Two-Step Process)

**IMPORTANT**: The application requires a two-step process to see trades in reports:

```bash
# Step 1: Ingest NDJSON file (stores executions in trades table)
uv run python main.py ingest file ../schwab-csv-to-json/output.ndjson

# Step 2: Process completed trades (matches buys with sells)
uv run python main.py db process-trades

# Step 3: View reports
uv run python main.py report trades
uv run python main.py report positions
```

#### Database Operations
```bash
# Run migrations
uv run python main.py db migrate

# Check database status
uv run python main.py db status

# Reset database (with confirmation)
uv run python main.py db reset --confirm

# Process completed trades (required after ingestion)
uv run python main.py db process-trades
uv run python main.py db process-trades --symbol AAPL
```

#### Data Ingestion
```bash
# Single file ingestion
uv run python main.py ingest file data.ndjson

# Batch processing
uv run python main.py ingest batch *.ndjson --output-summary

# Dry run (validation only)
uv run python main.py ingest file data.ndjson --dry-run

# Verbose processing
uv run python main.py ingest file data.ndjson --verbose
```

#### Reporting (Implemented)
```bash
# Dashboard analytics (comprehensive metrics)
uv run python main.py report dashboard
uv run python main.py report dashboard --date-range 2025-01-01,2025-01-31
uv run python main.py report dashboard --symbol AAPL
uv run python main.py report dashboard --format detailed  # Includes equity curve
uv run python main.py report dashboard --format json      # JSON export

# View completed trades
uv run python main.py report trades
uv run python main.py report trades --symbol AAPL
uv run python main.py report trades --format json

# View positions
uv run python main.py report positions
uv run python main.py report positions --open-only
uv run python main.py report positions --symbol AAPL
```

#### Pattern & Notes Management (Implemented)
```bash
# Pattern annotation
uv run python main.py pattern annotate --completed-trade-id 123 --pattern "MACD Scalp"
uv run python main.py pattern list
uv run python main.py pattern performance --pattern "MACD Scalp"

# Trade notes
uv run python main.py notes add --completed-trade-id 123 --text "Great entry timing"
uv run python main.py notes show --completed-trade-id 123
uv run python main.py notes edit --completed-trade-id 123 --text "Updated notes"
```

#### User Management (Admin-Only - Planned)
```bash
# List users with trade counts
uv run python main.py users list
uv run python main.py users list --all --format json

# Create users
uv run python main.py users create --username trader1 --email trader1@example.com
uv run python main.py users create --username admin2 --email admin2@example.com --admin

# Manage user status
uv run python main.py users deactivate --user-id 5
uv run python main.py users reactivate --user-id 5
uv run python main.py users make-admin --user-id 5
uv run python main.py users revoke-admin --user-id 5

# Delete users (with safety checks)
uv run python main.py users delete --user-id 5

# API key management
uv run python main.py users regenerate-key --user-id 5
```

## Technical Stack

- **Language**: Python 3.11+ (per pyproject.toml)
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
  "event_type": "fill",
  "asset_type": "STOCK",  // Valid values: STOCK, OPTION, ETF
  "source_file": "2025-11-04-TradeActivity.csv"
}
```

**Asset Type Mapping:**
- `STOCK` → `EQUITY` instrument_type
- `ETF` → `EQUITY` instrument_type (treated identically to STOCK)
- `OPTION` → `OPTION` instrument_type

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

## Task Management

This project uses a **tasks.md** file to enumerate all tasks required to implement the PRD. During implementation:
1. Create `tasks.md` with all implementation tasks broken down by phase
2. Mark tasks as complete using checkboxes as work progresses
3. Use this file to track progress and ensure comprehensive PRD implementation

## Key Development Guidelines

- **Test-Driven Development (TDD)**: All implementation must follow TDD methodology
- **Performance Target**: 10,000 records ingestion in < 5 seconds
- **Data Integrity**: Zero P&L calculation discrepancies on closed positions
- **Annotations**: Setup patterns and notes apply to completed trades, not individual executions
- **Error Handling**: Comprehensive transaction-based error recovery with rollback capabilities

## Related Projects

The application depends on output from the **Schwab CSV to JSON Converter** located at `../schwab-csv-to-json` for NDJSON input data.