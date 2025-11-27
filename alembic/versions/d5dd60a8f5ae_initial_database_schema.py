"""Initial database schema

Revision ID: d5dd60a8f5ae
Revises: 
Create Date: 2025-11-26 20:30:21.621134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd5dd60a8f5ae'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create completed_trades table
    op.create_table(
        'completed_trades',
        sa.Column('completed_trade_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('instrument_type', sa.String(10), nullable=False),
        sa.Column('option_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('total_qty', sa.Integer(), nullable=True),
        sa.Column('entry_avg_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('exit_avg_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('gross_proceeds', sa.Numeric(18, 8), nullable=True),
        sa.Column('gross_cost', sa.Numeric(18, 8), nullable=True),
        sa.Column('net_pnl', sa.Numeric(18, 8), nullable=True),
        sa.Column('opened_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('closed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('hold_duration', sa.Interval(), nullable=True),
        sa.Column('setup_pattern', sa.Text(), nullable=True),
        sa.Column('trade_notes', sa.Text(), nullable=True),
        sa.Column('strategy_category', sa.String(30), nullable=True),
        sa.Column('is_winning_trade', sa.Boolean(), nullable=True),
        sa.Column('trade_type', sa.String(20), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('completed_trade_id')
    )

    # Create trades table
    op.create_table(
        'trades',
        sa.Column('trade_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('unique_key', sa.Text(), nullable=False),
        sa.Column('exec_timestamp', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('event_type', sa.String(10), nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('instrument_type', sa.String(10), nullable=False),
        sa.Column('side', sa.String(10), nullable=True),
        sa.Column('qty', sa.Integer(), nullable=True),
        sa.Column('pos_effect', sa.String(10), nullable=True),
        sa.Column('price', sa.Numeric(18, 8), nullable=True),
        sa.Column('net_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('price_improvement', sa.Numeric(18, 8), nullable=True),
        sa.Column('order_type', sa.String(10), nullable=True),
        sa.Column('exp_date', sa.Date(), nullable=True),
        sa.Column('strike_price', sa.Numeric(18, 4), nullable=True),
        sa.Column('option_type', sa.String(4), nullable=True),
        sa.Column('spread_type', sa.String(20), nullable=True),
        sa.Column('option_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('platform_source', sa.String(20), server_default='TOS', nullable=True),
        sa.Column('source_file_path', sa.Text(), nullable=True),
        sa.Column('source_file_index', sa.Integer(), nullable=True),
        sa.Column('raw_data', sa.Text(), nullable=False),
        sa.Column('processing_timestamp', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('realized_pnl', sa.Numeric(18, 8), nullable=True),
        sa.Column('completed_trade_id', sa.BigInteger(), nullable=True),
        sa.CheckConstraint("instrument_type IN ('EQUITY', 'OPTION')", name='valid_instrument_type'),
        sa.CheckConstraint("side IN ('BUY', 'SELL') OR side IS NULL", name='valid_side'),
        sa.CheckConstraint("event_type IN ('fill', 'cancel', 'amend')", name='valid_event_type'),
        sa.ForeignKeyConstraint(['completed_trade_id'], ['completed_trades.completed_trade_id'], ),
        sa.PrimaryKeyConstraint('trade_id'),
        sa.UniqueConstraint('unique_key')
    )

    # Create positions table
    op.create_table(
        'positions',
        sa.Column('position_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('instrument_type', sa.String(10), nullable=False),
        sa.Column('option_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('current_qty', sa.Integer(), server_default='0', nullable=True),
        sa.Column('avg_cost_basis', sa.Numeric(18, 8), nullable=True),
        sa.Column('total_cost', sa.Numeric(18, 8), nullable=True),
        sa.Column('opened_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('closed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('realized_pnl', sa.Numeric(18, 8), server_default='0', nullable=True),
        sa.PrimaryKeyConstraint('position_id'),
        sa.UniqueConstraint('symbol', 'instrument_type', 'option_details', name='unique_position')
    )

    # Create setup_patterns table
    op.create_table(
        'setup_patterns',
        sa.Column('pattern_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pattern_name', sa.String(50), nullable=False),
        sa.Column('pattern_description', sa.Text(), nullable=True),
        sa.Column('pattern_category', sa.String(30), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('pattern_id')
    )

    # Create processing_log table
    op.create_table(
        'processing_log',
        sa.Column('log_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('processing_started_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('processing_completed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('records_processed', sa.Integer(), server_default='0', nullable=True),
        sa.Column('records_failed', sa.Integer(), server_default='0', nullable=True),
        sa.Column('status', sa.String(20), server_default='processing', nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('log_id'),
        sa.UniqueConstraint('file_path', 'processing_started_at', name='unique_processing_attempt')
    )

    # Create ohlcv_price_series table (future ready)
    op.create_table(
        'ohlcv_price_series',
        sa.Column('series_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('timestamp', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('timeframe', sa.String(10), nullable=False),
        sa.Column('open_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('high_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('low_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('close_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('volume', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('series_id')
    )

    # Create indexes for performance
    op.create_index('idx_trades_exec_timestamp', 'trades', ['exec_timestamp'])
    op.create_index('idx_trades_symbol', 'trades', ['symbol'])
    op.create_index('idx_trades_symbol_timestamp', 'trades', ['symbol', 'exec_timestamp'])
    op.create_index('idx_trades_instrument_type', 'trades', ['instrument_type'])
    op.create_index('idx_trades_symbol_pos_effect', 'trades', ['symbol', 'pos_effect', 'exec_timestamp'])
    op.create_index('idx_trades_open_positions', 'trades', ['symbol', 'pos_effect'], postgresql_where=sa.text("pos_effect = 'TO OPEN'"))
    op.create_index('idx_trades_source_file', 'trades', ['source_file_path'])
    op.create_index('idx_positions_symbol', 'positions', ['symbol'])
    op.create_index('idx_positions_open', 'positions', ['symbol'], postgresql_where=sa.text('closed_at IS NULL'))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_positions_open', 'positions')
    op.drop_index('idx_positions_symbol', 'positions')
    op.drop_index('idx_trades_source_file', 'trades')
    op.drop_index('idx_trades_open_positions', 'trades')
    op.drop_index('idx_trades_symbol_pos_effect', 'trades')
    op.drop_index('idx_trades_instrument_type', 'trades')
    op.drop_index('idx_trades_symbol_timestamp', 'trades')
    op.drop_index('idx_trades_symbol', 'trades')
    op.drop_index('idx_trades_exec_timestamp', 'trades')

    # Drop tables
    op.drop_table('ohlcv_price_series')
    op.drop_table('processing_log')
    op.drop_table('setup_patterns')
    op.drop_table('positions')
    op.drop_table('trades')
    op.drop_table('completed_trades')
