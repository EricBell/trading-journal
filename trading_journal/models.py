"""SQLAlchemy models for trading journal database schema."""

from datetime import datetime, date
from typing import Optional, Dict, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Integer,
    Interval,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Trade(Base):
    """Individual executions/fills table (trades in PRD terminology)."""

    __tablename__ = "trades"

    # Primary key
    trade_id = Column(BigInteger, primary_key=True, autoincrement=True)
    unique_key = Column(Text, unique=True, nullable=False)

    # Execution details
    exec_timestamp = Column(TIMESTAMP(timezone=True))
    event_type = Column(String(10), nullable=False)

    # Instrument details
    symbol = Column(String(50), nullable=False)
    instrument_type = Column(String(10), nullable=False)

    # Trade details
    side = Column(String(10))
    qty = Column(Integer)
    pos_effect = Column(String(10))

    # Pricing
    price = Column(Numeric(18, 8))
    net_price = Column(Numeric(18, 8))
    price_improvement = Column(Numeric(18, 8))
    order_type = Column(String(10))

    # Options data (nullable for equities)
    exp_date = Column(Date)
    strike_price = Column(Numeric(18, 4))
    option_type = Column(String(4))
    spread_type = Column(String(20))
    option_data = Column(JSONB)

    # Processing metadata
    platform_source = Column(String(20), default="TOS")
    source_file_path = Column(Text)
    source_file_index = Column(Integer)
    raw_data = Column(Text, nullable=False)
    processing_timestamp = Column(TIMESTAMP(timezone=True), default=func.now())

    # P&L tracking
    realized_pnl = Column(Numeric(18, 8))

    # Trade relationship
    completed_trade_id = Column(BigInteger, ForeignKey("completed_trades.completed_trade_id"))

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "instrument_type IN ('EQUITY', 'OPTION')",
            name="valid_instrument_type"
        ),
        CheckConstraint(
            "side IN ('BUY', 'SELL') OR side IS NULL",
            name="valid_side"
        ),
        CheckConstraint(
            "event_type IN ('fill', 'cancel', 'amend')",
            name="valid_event_type"
        ),
    )

    # Relationship
    completed_trade = relationship("CompletedTrade", back_populates="executions")

    @property
    def is_fill(self) -> bool:
        """Check if this is a fill execution."""
        return self.event_type == 'fill' and self.exec_timestamp is not None


class CompletedTrade(Base):
    """Complete round-trip trades table."""

    __tablename__ = "completed_trades"

    # Primary key
    completed_trade_id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False)
    instrument_type = Column(String(10), nullable=False)
    option_details = Column(JSONB)

    # Trade summary
    total_qty = Column(Integer)
    entry_avg_price = Column(Numeric(18, 8))
    exit_avg_price = Column(Numeric(18, 8))
    gross_proceeds = Column(Numeric(18, 8))
    gross_cost = Column(Numeric(18, 8))
    net_pnl = Column(Numeric(18, 8))

    # Trade timeline
    opened_at = Column(TIMESTAMP(timezone=True))
    closed_at = Column(TIMESTAMP(timezone=True))
    hold_duration = Column(Interval)

    # Trading analysis
    setup_pattern = Column(Text)
    trade_notes = Column(Text)
    strategy_category = Column(String(30))

    # Trade classification
    is_winning_trade = Column(Boolean)
    trade_type = Column(String(20))
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    executions = relationship("Trade", back_populates="completed_trade")


class Position(Base):
    """Current holdings aggregate table."""

    __tablename__ = "positions"

    # Primary key
    position_id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False)
    instrument_type = Column(String(10), nullable=False)
    option_details = Column(JSONB)

    # Position state
    current_qty = Column(Integer, default=0)
    avg_cost_basis = Column(Numeric(18, 8))
    total_cost = Column(Numeric(18, 8))

    # Timestamps
    opened_at = Column(TIMESTAMP(timezone=True))
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())
    closed_at = Column(TIMESTAMP(timezone=True))

    # P&L tracking
    realized_pnl = Column(Numeric(18, 8), default=0)

    # Unique constraint
    __table_args__ = (
        UniqueConstraint("symbol", "instrument_type", "option_details", name="unique_position"),
    )


class SetupPattern(Base):
    """Setup patterns management table (production version)."""

    __tablename__ = "setup_patterns"

    # Primary key
    pattern_id = Column(BigInteger, primary_key=True, autoincrement=True)
    pattern_name = Column(String(50), nullable=False)
    pattern_description = Column(Text)
    pattern_category = Column(String(30))
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())


class ProcessingLog(Base):
    """File processing audit trail table."""

    __tablename__ = "processing_log"

    # Primary key
    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    file_path = Column(Text, nullable=False)
    processing_started_at = Column(TIMESTAMP(timezone=True), default=func.now())
    processing_completed_at = Column(TIMESTAMP(timezone=True))
    records_processed = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    status = Column(String(20), default="processing")
    error_message = Column(Text)

    # Unique constraint
    __table_args__ = (
        UniqueConstraint("file_path", "processing_started_at", name="unique_processing_attempt"),
    )


class OhlcvPriceSeries(Base):
    """Future-ready price data table (empty for MVP)."""

    __tablename__ = "ohlcv_price_series"

    # Primary key
    series_id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)
    timeframe = Column(String(10), nullable=False)
    open_price = Column(Numeric(18, 8))
    high_price = Column(Numeric(18, 8))
    low_price = Column(Numeric(18, 8))
    close_price = Column(Numeric(18, 8))
    volume = Column(Integer)