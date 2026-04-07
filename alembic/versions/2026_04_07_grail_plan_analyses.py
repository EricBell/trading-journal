"""Add grail_plan_analyses table for zone-based plan analysis

Revision ID: 2026_04_07_grail_plan_analyses
Revises: 2026_04_01_grail_plan_override
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2026_04_07_grail_plan_analyses"
down_revision: Union[str, None] = "2026_04_01_grail_plan_override"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "grail_plan_analyses" not in existing_tables:
        op.create_table(
            "grail_plan_analyses",
            sa.Column("grail_plan_analyses_id", sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
            # External grail plan identity
            sa.Column("grail_plan_id", sa.Text, nullable=False),
            # Plan parameters snapshotted at analysis time
            sa.Column("symbol", sa.String(50), nullable=False),
            sa.Column("asset_type", sa.String(20), nullable=True),
            sa.Column("side", sa.String(10), nullable=True),
            sa.Column("entry_zone_low", sa.Numeric(18, 8), nullable=True),
            sa.Column("entry_zone_high", sa.Numeric(18, 8), nullable=True),
            sa.Column("entry_ideal", sa.Numeric(18, 8), nullable=True),
            sa.Column("stop_zone_low", sa.Numeric(18, 8), nullable=True),
            sa.Column("stop_zone_high", sa.Numeric(18, 8), nullable=True),
            sa.Column("tp1_zone_low", sa.Numeric(18, 8), nullable=True),
            sa.Column("tp1_zone_high", sa.Numeric(18, 8), nullable=True),
            # Fetch details
            sa.Column("fetch_start_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("fetch_end_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("bars_fetched", sa.Integer, nullable=True),
            sa.Column("fetch_status", sa.String(20), nullable=True),
            # Analysis
            sa.Column("analysis_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("bars_scanned", sa.Integer, nullable=True),
            # Entry behavior
            sa.Column("entry_zone_touched", sa.Boolean, nullable=True),
            sa.Column("entry_ideal_touched", sa.Boolean, nullable=True),
            sa.Column("entry_first_touch_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("bars_to_entry", sa.Integer, nullable=True),
            # Outcome
            sa.Column("outcome", sa.String(20), nullable=True),
            sa.Column("tp1_zone_touched", sa.Boolean, nullable=True),
            sa.Column("tp1_zone_touch_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("stop_zone_touched", sa.Boolean, nullable=True),
            sa.Column("stop_zone_touch_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("bars_to_outcome", sa.Integer, nullable=True),
            sa.Column("analyzed_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint(
                "outcome IN ('no_entry', 'success', 'failure', 'inconclusive')",
                name="chk_gpa_outcome",
            ),
            sa.UniqueConstraint("grail_plan_id", "analysis_version", name="uq_grail_plan_analyses_version"),
        )


def downgrade() -> None:
    op.drop_table("grail_plan_analyses")
