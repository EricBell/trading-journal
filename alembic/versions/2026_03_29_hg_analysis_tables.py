"""Add hg_market_data_requests and hg_analysis_results tables

Revision ID: 2026_03_29_hg_analysis
Revises: 2026_03_28_ohlcv_vwap
Create Date: 2026-03-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "2026_03_29_hg_analysis"
down_revision: Union[str, None] = "2026_03_28_ohlcv_vwap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "hg_market_data_requests" not in existing_tables:
        op.create_table(
            "hg_market_data_requests",
            sa.Column("hg_market_data_request_id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
            # External grail plan identity
            sa.Column("grail_plan_id", sa.Text, nullable=False),
            sa.Column("grail_plan_created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            # Optional local link to a matched trade
            sa.Column(
                "completed_trade_id",
                sa.BigInteger,
                sa.ForeignKey("completed_trades.completed_trade_id", ondelete="SET NULL"),
                nullable=True,
            ),
            # Market data request identity
            sa.Column("symbol", sa.Text, nullable=False),
            sa.Column("timeframe", sa.Text, nullable=False),
            sa.Column("fetch_start_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("fetch_end_at", sa.TIMESTAMP(timezone=True), nullable=False),
            # Window provenance
            sa.Column("request_source", sa.Text, nullable=False, server_default="manual"),
            sa.Column("window_rule", sa.Text, nullable=False),
            sa.Column("linked_trade_exit_at", sa.TIMESTAMP(timezone=True), nullable=True),
            # Fetch result bookkeeping
            sa.Column("status", sa.Text, nullable=False, server_default="pending"),
            sa.Column("bars_expected", sa.Integer, nullable=True),
            sa.Column("bars_received", sa.Integer, nullable=True),
            sa.Column("first_bar_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("last_bar_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("provider", sa.Text, nullable=False, server_default="massive"),
            sa.Column("provider_request_meta", JSONB, nullable=False, server_default="{}"),
            sa.Column("error_text", sa.Text, nullable=True),
            sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
            # Constraints
            sa.CheckConstraint("timeframe IN ('1m', '5m', '15m', '1d')", name="chk_hg_mdr_timeframe"),
            sa.CheckConstraint("status IN ('pending', 'success', 'partial', 'failed')", name="chk_hg_mdr_status"),
            sa.CheckConstraint("request_source IN ('manual', 'batch', 'trade_linked')", name="chk_hg_mdr_source"),
            sa.CheckConstraint("fetch_end_at > fetch_start_at", name="chk_hg_mdr_window"),
            sa.UniqueConstraint(
                "user_id", "grail_plan_id", "timeframe", "fetch_start_at", "fetch_end_at",
                name="uq_hg_market_data_request_window",
            ),
        )
        op.create_index(
            "ix_hg_market_data_requests_user_created",
            "hg_market_data_requests",
            ["user_id", sa.text("created_at DESC")],
        )
        op.create_index(
            "ix_hg_market_data_requests_plan",
            "hg_market_data_requests",
            ["user_id", "grail_plan_id"],
        )
        op.create_index(
            "ix_hg_market_data_requests_trade",
            "hg_market_data_requests",
            ["completed_trade_id"],
        )
        op.create_index(
            "ix_hg_market_data_requests_symbol_time",
            "hg_market_data_requests",
            ["symbol", "timeframe", "fetch_start_at", "fetch_end_at"],
        )

    if "hg_analysis_results" not in existing_tables:
        op.create_table(
            "hg_analysis_results",
            sa.Column("hg_analysis_result_id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "hg_market_data_request_id",
                sa.BigInteger,
                sa.ForeignKey("hg_market_data_requests.hg_market_data_request_id", ondelete="CASCADE"),
                nullable=False,
            ),
            # Denormalized external identity for easy querying
            sa.Column("grail_plan_id", sa.Text, nullable=False),
            sa.Column("grail_plan_created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column(
                "completed_trade_id",
                sa.BigInteger,
                sa.ForeignKey("completed_trades.completed_trade_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("symbol", sa.Text, nullable=False),
            sa.Column("timeframe", sa.Text, nullable=False),
            sa.Column("analysis_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("evaluated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
            # Plan parameters captured at evaluation time
            sa.Column("side", sa.Text, nullable=False),
            sa.Column("instrument_type", sa.Text, nullable=False),
            sa.Column("entry_zone_low", sa.Numeric(18, 8), nullable=False),
            sa.Column("entry_zone_high", sa.Numeric(18, 8), nullable=False),
            sa.Column("target_1_price", sa.Numeric(18, 8), nullable=True),
            sa.Column("target_2_price", sa.Numeric(18, 8), nullable=True),
            sa.Column("stop_price", sa.Numeric(18, 8), nullable=True),
            # Evaluation window
            sa.Column("eval_start_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("eval_end_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("bars_scanned", sa.Integer, nullable=False, server_default="0"),
            # Entry behavior
            sa.Column("entry_touched", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("entry_first_touch_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("entry_touch_type", sa.Text, nullable=False, server_default="never"),
            sa.Column("entry_touch_price", sa.Numeric(18, 8), nullable=True),
            # Target behavior
            sa.Column("tp1_reached", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("tp1_reached_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("tp2_reached", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("tp2_reached_at", sa.TIMESTAMP(timezone=True), nullable=True),
            # Excursion metrics
            sa.Column("max_favorable_excursion", sa.Numeric(18, 8), nullable=True),
            sa.Column("max_adverse_excursion", sa.Numeric(18, 8), nullable=True),
            sa.Column("mfe_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("mae_at", sa.TIMESTAMP(timezone=True), nullable=True),
            # Timing metrics
            sa.Column("bars_to_entry", sa.Integer, nullable=True),
            sa.Column("bars_from_entry_to_tp1", sa.Integer, nullable=True),
            sa.Column("bars_from_entry_to_tp2", sa.Integer, nullable=True),
            # Trade comparison hooks
            sa.Column("linked_trade_opened_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("linked_trade_closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("linked_trade_entry_price", sa.Numeric(18, 8), nullable=True),
            sa.Column("linked_trade_exit_price", sa.Numeric(18, 8), nullable=True),
            sa.Column("notes", JSONB, nullable=False, server_default="{}"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
            # Constraints
            sa.CheckConstraint("timeframe IN ('1m', '5m', '15m', '1d')", name="chk_hg_ar_timeframe"),
            sa.CheckConstraint("side IN ('long', 'short')", name="chk_hg_ar_side"),
            sa.CheckConstraint("instrument_type IN ('equity', 'option')", name="chk_hg_ar_instrument_type"),
            sa.CheckConstraint(
                "entry_touch_type IN ('never', 'top_of_zone', 'in_zone', 'bottom_of_zone', 'through_zone')",
                name="chk_hg_ar_touch_type",
            ),
            sa.CheckConstraint("eval_end_at > eval_start_at", name="chk_hg_ar_eval_window"),
            sa.CheckConstraint("entry_zone_high >= entry_zone_low", name="chk_hg_ar_entry_zone"),
            sa.UniqueConstraint(
                "hg_market_data_request_id", "analysis_version",
                name="uq_hg_analysis_results_version",
            ),
        )
        op.create_index(
            "ix_hg_analysis_results_user_plan",
            "hg_analysis_results",
            ["user_id", "grail_plan_id"],
        )
        op.create_index(
            "ix_hg_analysis_results_trade",
            "hg_analysis_results",
            ["completed_trade_id"],
        )
        op.create_index(
            "ix_hg_analysis_results_symbol_eval",
            "hg_analysis_results",
            ["symbol", "eval_start_at", "eval_end_at"],
        )
        op.create_index(
            "ix_hg_analysis_results_outcomes",
            "hg_analysis_results",
            ["user_id", "entry_touched", "tp1_reached", "tp2_reached"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "hg_analysis_results" in existing_tables:
        op.drop_table("hg_analysis_results")

    if "hg_market_data_requests" in existing_tables:
        op.drop_table("hg_market_data_requests")
