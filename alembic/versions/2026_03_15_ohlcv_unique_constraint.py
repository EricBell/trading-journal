"""Add unique constraint to ohlcv_price_series (symbol, timestamp, timeframe)

Revision ID: 2026_03_15_ohlcv_uc
Revises: 2026_03_14_ann_ctx
Create Date: 2026-03-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '2026_03_15_ohlcv_uc'
down_revision: Union[str, Sequence[str], None] = '2026_03_14_ann_ctx'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {uc['name'] for uc in inspector.get_unique_constraints('ohlcv_price_series')}
    if 'uq_ohlcv_symbol_ts_tf' not in existing:
        op.create_unique_constraint(
            'uq_ohlcv_symbol_ts_tf',
            'ohlcv_price_series',
            ['symbol', 'timestamp', 'timeframe'],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {uc['name'] for uc in inspector.get_unique_constraints('ohlcv_price_series')}
    if 'uq_ohlcv_symbol_ts_tf' in existing:
        op.drop_constraint('uq_ohlcv_symbol_ts_tf', 'ohlcv_price_series', type_='unique')
