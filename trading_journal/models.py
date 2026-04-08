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
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class SetupSource(Base):
    """Setup sources management table (e.g. broker, scanner, alert service)."""

    __tablename__ = "setup_sources"

    # Primary key
    source_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # User relationship
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    source_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="setup_sources")
    # Unique index (case-insensitive) is managed by Alembic: uq_source_per_user


class User(Base):
    """User accounts table for multi-user support."""

    __tablename__ = "users"

    # Primary key
    user_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # User credentials and identity
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255))  # Nullable for API key-only users

    # Authentication method
    auth_method = Column(String(20), default="api_key", nullable=False)

    # User status
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)

    # API key authentication
    api_key_hash = Column(String(64), unique=True)  # SHA256 hash
    api_key_created_at = Column(TIMESTAMP(timezone=True))

    # User preferences
    timezone = Column(String(50), default='US/Eastern')

    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())
    last_login_at = Column(TIMESTAMP(timezone=True))

    # Relationships
    trades = relationship("Trade", back_populates="user")
    completed_trades = relationship("CompletedTrade", back_populates="user")
    positions = relationship("Position", back_populates="user")
    accounts = relationship("Account", back_populates="user")
    setup_patterns = relationship("SetupPattern", back_populates="user")
    setup_sources = relationship("SetupSource", back_populates="user")
    processing_logs = relationship("ProcessingLog", back_populates="user")
    trade_annotations = relationship("TradeAnnotation", back_populates="user")
    journal_notes = relationship("JournalNote", back_populates="user", order_by="JournalNote.created_at.desc()")
    hg_market_data_requests = relationship("HgMarketDataRequest", back_populates="user")
    hg_analysis_results = relationship("HgAnalysisResult", back_populates="user")
    grail_plan_analyses = relationship("GrailPlanAnalysis", back_populates="user")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "auth_method IN ('api_key', 'jwt', 'oauth', 'session')",
            name="valid_auth_method"
        ),
    )


class Account(Base):
    """Brokerage accounts table for multi-account support."""

    __tablename__ = "accounts"

    account_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    account_number = Column(String(50), nullable=False)
    account_name = Column(String(100))
    account_type = Column(String(50))
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="accounts")

    __table_args__ = (
        UniqueConstraint("user_id", "account_number", name="unique_account_per_user"),
    )


class Trade(Base):
    """Individual executions/fills table (trades in PRD terminology)."""

    __tablename__ = "trades"

    # Primary key
    trade_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # User relationship
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    # Account relationship
    account_id = Column(BigInteger, ForeignKey("accounts.account_id"), nullable=True)

    unique_key = Column(Text, nullable=False)

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
        UniqueConstraint("user_id", "unique_key", name="unique_trade_per_user"),
        CheckConstraint(
            "instrument_type IN ('EQUITY', 'OPTION', 'FUTURES')",
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

    # Relationships
    user = relationship("User", back_populates="trades")
    account = relationship("Account")
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

    # User relationship
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    # Account relationship
    account_id = Column(BigInteger, ForeignKey("accounts.account_id"), nullable=True)

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

    # Trade classification
    is_winning_trade = Column(Boolean)
    trade_type = Column(String(20))
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="completed_trades")
    account = relationship("Account")
    executions = relationship("Trade", back_populates="completed_trade")
    trade_annotation = relationship("TradeAnnotation", uselist=False, back_populates="trade")

    @property
    def option_details_dict(self) -> Optional[Dict[str, Any]]:
        """Return option_details as a dict, handling legacy JSON string storage."""
        if self.option_details is None:
            return None
        if isinstance(self.option_details, str):
            import json as _json
            try:
                return _json.loads(self.option_details)
            except (ValueError, TypeError):
                return None
        return self.option_details


class TradeAnnotation(Base):
    """Manually entered trade annotation data — survives completed_trades resets."""

    __tablename__ = "trade_annotations"

    annotation_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # FK to completed_trades — nullable so annotations survive table drops
    completed_trade_id = Column(
        BigInteger,
        ForeignKey("completed_trades.completed_trade_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Natural key — used to re-link after a completed_trades reset
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    symbol = Column(String(50), nullable=False)
    opened_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # Annotation fields
    setup_pattern_id = Column(BigInteger, ForeignKey("setup_patterns.pattern_id"), nullable=True)
    setup_source_id = Column(BigInteger, ForeignKey("setup_sources.source_id"), nullable=True)
    stop_price = Column(Numeric(18, 8), nullable=True)
    trade_notes = Column(Text, nullable=True)
    strategy_category = Column(String(30), nullable=True)
    atm_engaged = Column(String(20), nullable=True)
    exit_reason = Column(String(30), nullable=True)
    underlying_at_entry = Column(Numeric(18, 8), nullable=True)

    # Grail plan override — user-selected plan ID or explicit rejection flag
    grail_plan_id = Column(Integer, nullable=True)
    grail_plan_rejected = Column(Boolean, nullable=False, server_default="false", default=False)

    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    trade = relationship("CompletedTrade", back_populates="trade_annotation")
    user = relationship("User", back_populates="trade_annotations")
    setup_pattern_rel = relationship("SetupPattern", foreign_keys=[setup_pattern_id])
    setup_source_rel = relationship("SetupSource", foreign_keys=[setup_source_id])

    __table_args__ = (
        UniqueConstraint("user_id", "symbol", "opened_at", name="uq_annotation_per_trade"),
    )


class Position(Base):
    """Current holdings aggregate table."""

    __tablename__ = "positions"

    # Primary key
    position_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # User relationship
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    # Account relationship
    account_id = Column(BigInteger, ForeignKey("accounts.account_id"), nullable=True)

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

    # Relationships
    user = relationship("User", back_populates="positions")
    account = relationship("Account")

    # Unique constraint — account_id scopes positions per brokerage account.
    # Note: PostgreSQL treats NULLs as distinct in unique indexes, so two rows with
    # account_id=NULL and the same other keys will not conflict at the DB level.
    # Correctness for null-account positions is enforced by the delete-then-rebuild
    # logic in PositionTracker, not by the constraint alone.
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", "instrument_type", "option_details", "account_id", name="unique_position_per_user"),
    )


class SetupPattern(Base):
    """Setup patterns management table (production version)."""

    __tablename__ = "setup_patterns"

    # Primary key
    pattern_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # User relationship
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    pattern_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="setup_patterns")

    # Unique index (case-insensitive) is managed by Alembic: uq_pattern_per_user


class ProcessingLog(Base):
    """File processing audit trail table."""

    __tablename__ = "processing_log"

    # Primary key
    log_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # User relationship
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)

    file_path = Column(Text, nullable=False)
    processing_started_at = Column(TIMESTAMP(timezone=True), default=func.now())
    processing_completed_at = Column(TIMESTAMP(timezone=True))
    records_processed = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    status = Column(String(20), default="processing")
    error_message = Column(Text)

    # Relationships
    user = relationship("User", back_populates="processing_logs")

    # Unique constraint
    __table_args__ = (
        UniqueConstraint("user_id", "file_path", "processing_started_at", name="unique_processing_attempt_per_user"),
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
    vwap = Column(Numeric(18, 8))


class JournalNote(Base):
    """Free-form timestamped notes for the trader (not tied to any trade)."""

    __tablename__ = "journal_notes"

    note_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    title = Column(String(200), nullable=True)
    body = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="journal_notes")


class HgMarketDataRequest(Base):
    """Audit trail of historical market-data fetches requested for a specific HG plan."""

    __tablename__ = "hg_market_data_requests"

    hg_market_data_request_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)

    # External grail plan identity
    grail_plan_id = Column(Text, nullable=False)
    grail_plan_created_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # Optional local link to a matched trade
    completed_trade_id = Column(
        BigInteger,
        ForeignKey("completed_trades.completed_trade_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Market data request identity
    symbol = Column(String(50), nullable=False)
    timeframe = Column(String(10), nullable=False)
    fetch_start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    fetch_end_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # Window provenance
    request_source = Column(String(20), nullable=False, default="manual")
    window_rule = Column(String(50), nullable=False)
    linked_trade_exit_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Fetch result bookkeeping
    status = Column(String(20), nullable=False, default="pending")
    bars_expected = Column(Integer, nullable=True)
    bars_received = Column(Integer, nullable=True)
    first_bar_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_bar_at = Column(TIMESTAMP(timezone=True), nullable=True)
    provider = Column(String(50), nullable=False, default="massive")
    provider_request_meta = Column(JSONB, nullable=False, default=dict)
    error_text = Column(Text, nullable=True)
    fetched_at = Column(TIMESTAMP(timezone=True), nullable=True)

    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("timeframe IN ('1m', '5m', '15m', '1d')", name="chk_hg_mdr_timeframe"),
        CheckConstraint("status IN ('pending', 'success', 'partial', 'failed')", name="chk_hg_mdr_status"),
        CheckConstraint("request_source IN ('manual', 'batch', 'trade_linked')", name="chk_hg_mdr_source"),
        CheckConstraint("fetch_end_at > fetch_start_at", name="chk_hg_mdr_window"),
        UniqueConstraint(
            "user_id", "grail_plan_id", "timeframe", "fetch_start_at", "fetch_end_at",
            name="uq_hg_market_data_request_window",
        ),
    )

    user = relationship("User", back_populates="hg_market_data_requests")
    analysis_results = relationship("HgAnalysisResult", back_populates="market_data_request")


class HgAnalysisResult(Base):
    """Versioned, deterministic evaluation results for an HG plan against fetched market data."""

    __tablename__ = "hg_analysis_results"

    hg_analysis_result_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    hg_market_data_request_id = Column(
        BigInteger,
        ForeignKey("hg_market_data_requests.hg_market_data_request_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Denormalized external identity for easy querying
    grail_plan_id = Column(Text, nullable=False)
    grail_plan_created_at = Column(TIMESTAMP(timezone=True), nullable=False)

    completed_trade_id = Column(
        BigInteger,
        ForeignKey("completed_trades.completed_trade_id", ondelete="SET NULL"),
        nullable=True,
    )

    symbol = Column(String(50), nullable=False)
    timeframe = Column(String(10), nullable=False)
    analysis_version = Column(Integer, nullable=False, default=1)
    evaluated_at = Column(TIMESTAMP(timezone=True), default=func.now())

    # Plan parameters captured at evaluation time
    side = Column(String(10), nullable=False)
    instrument_type = Column(String(10), nullable=False)
    entry_zone_low = Column(Numeric(18, 8), nullable=False)
    entry_zone_high = Column(Numeric(18, 8), nullable=False)
    target_1_price = Column(Numeric(18, 8), nullable=True)
    target_2_price = Column(Numeric(18, 8), nullable=True)
    stop_price = Column(Numeric(18, 8), nullable=True)

    # Evaluation window
    eval_start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    eval_end_at = Column(TIMESTAMP(timezone=True), nullable=False)
    bars_scanned = Column(Integer, nullable=False, default=0)

    # Entry behavior
    entry_touched = Column(Boolean, nullable=False, default=False)
    entry_first_touch_at = Column(TIMESTAMP(timezone=True), nullable=True)
    entry_touch_type = Column(String(20), nullable=False, default="never")
    entry_touch_price = Column(Numeric(18, 8), nullable=True)

    # Target behavior
    tp1_reached = Column(Boolean, nullable=False, default=False)
    tp1_reached_at = Column(TIMESTAMP(timezone=True), nullable=True)
    tp2_reached = Column(Boolean, nullable=False, default=False)
    tp2_reached_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Excursion metrics
    max_favorable_excursion = Column(Numeric(18, 8), nullable=True)
    max_adverse_excursion = Column(Numeric(18, 8), nullable=True)
    mfe_at = Column(TIMESTAMP(timezone=True), nullable=True)
    mae_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Timing metrics
    bars_to_entry = Column(Integer, nullable=True)
    bars_from_entry_to_tp1 = Column(Integer, nullable=True)
    bars_from_entry_to_tp2 = Column(Integer, nullable=True)

    # Trade comparison hooks for later UI
    linked_trade_opened_at = Column(TIMESTAMP(timezone=True), nullable=True)
    linked_trade_closed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    linked_trade_entry_price = Column(Numeric(18, 8), nullable=True)
    linked_trade_exit_price = Column(Numeric(18, 8), nullable=True)

    notes = Column(JSONB, nullable=False, default=dict)

    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("timeframe IN ('1m', '5m', '15m', '1d')", name="chk_hg_ar_timeframe"),
        CheckConstraint("side IN ('long', 'short')", name="chk_hg_ar_side"),
        CheckConstraint("instrument_type IN ('equity', 'option')", name="chk_hg_ar_instrument_type"),
        CheckConstraint(
            "entry_touch_type IN ('never', 'top_of_zone', 'in_zone', 'bottom_of_zone', 'through_zone')",
            name="chk_hg_ar_touch_type",
        ),
        CheckConstraint("eval_end_at > eval_start_at", name="chk_hg_ar_eval_window"),
        CheckConstraint("entry_zone_high >= entry_zone_low", name="chk_hg_ar_entry_zone"),
        UniqueConstraint(
            "hg_market_data_request_id", "analysis_version",
            name="uq_hg_analysis_results_version",
        ),
    )

    user = relationship("User", back_populates="hg_analysis_results")
    market_data_request = relationship("HgMarketDataRequest", back_populates="analysis_results")


class GrailPlanAnalysis(Base):
    """Zone-based analysis of a grail plan against 1-min OHLCV bar data.

    Plan-centric (not trade-linked): evaluates whether price entered the entry zone,
    hit the ideal entry, and then reached TP1 before the stop zone. Results are
    keyed by (grail_plan_id, analysis_version) — shared across users.
    """

    __tablename__ = "grail_plan_analyses"

    grail_plan_analyses_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)

    # External grail plan identity
    grail_plan_id = Column(Text, nullable=False)

    # Plan parameters snapshotted at analysis time
    symbol = Column(String(50), nullable=False)
    asset_type = Column(String(20), nullable=True)   # STOCK, OPTIONS, FUTURES
    side = Column(String(10), nullable=True)          # long, short
    entry_zone_low = Column(Numeric(18, 8), nullable=True)
    entry_zone_high = Column(Numeric(18, 8), nullable=True)
    entry_ideal = Column(Numeric(18, 8), nullable=True)   # entry_price / zone mid
    stop_zone_low = Column(Numeric(18, 8), nullable=True)
    stop_zone_high = Column(Numeric(18, 8), nullable=True)
    tp1_zone_low = Column(Numeric(18, 8), nullable=True)
    tp1_zone_high = Column(Numeric(18, 8), nullable=True)

    # Fetch details
    fetch_start_at = Column(TIMESTAMP(timezone=True), nullable=True)
    fetch_end_at = Column(TIMESTAMP(timezone=True), nullable=True)
    bars_fetched = Column(Integer, nullable=True)
    bars_expected = Column(Integer, nullable=True)   # expected market-hours bars in window
    fetch_status = Column(String(20), nullable=True)   # success, partial, failed, skipped

    # Analysis
    analysis_version = Column(Integer, nullable=False, default=1)
    bars_scanned = Column(Integer, nullable=True)

    # Entry behavior
    entry_zone_touched = Column(Boolean, nullable=True)
    entry_ideal_touched = Column(Boolean, nullable=True)
    entry_first_touch_at = Column(TIMESTAMP(timezone=True), nullable=True)
    bars_to_entry = Column(Integer, nullable=True)

    # Outcome
    outcome = Column(String(20), nullable=True)   # no_entry | success | failure | inconclusive
    tp1_zone_touched = Column(Boolean, nullable=True)
    tp1_zone_touch_at = Column(TIMESTAMP(timezone=True), nullable=True)
    stop_zone_touched = Column(Boolean, nullable=True)
    stop_zone_touch_at = Column(TIMESTAMP(timezone=True), nullable=True)
    bars_to_outcome = Column(Integer, nullable=True)

    analyzed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('no_data', 'no_entry', 'success', 'failure', 'inconclusive', 'invalid')",
            name="chk_gpa_outcome",
        ),
        UniqueConstraint("grail_plan_id", "analysis_version", name="uq_grail_plan_analyses_version"),
    )

    user = relationship("User", back_populates="grail_plan_analyses")