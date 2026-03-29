"""Add vwap column to ohlcv_price_series

Revision ID: 2026_03_28_ohlcv_vwap
Revises: 2026_03_26_futures
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "2026_03_28_ohlcv_vwap"
down_revision: Union[str, None] = "2026_03_26_futures"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ohlcv_price_series",
        sa.Column("vwap", sa.Numeric(18, 8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ohlcv_price_series", "vwap")
