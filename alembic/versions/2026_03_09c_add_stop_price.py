"""add missing stop_price column to completed_trades

Revision ID: 2026_03_09c_stop_price
Revises: 2026_03_09b_fix_schema
Create Date: 2026-03-09 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '2026_03_09c_stop_price'
down_revision: Union[str, Sequence[str], None] = '2026_03_09b_fix_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = {c['name'] for c in sa.inspect(conn).get_columns('completed_trades')}
    if 'stop_price' not in cols:
        op.add_column(
            'completed_trades',
            sa.Column('stop_price', sa.Numeric(18, 8), nullable=True)
        )


def downgrade() -> None:
    conn = op.get_bind()
    cols = {c['name'] for c in sa.inspect(conn).get_columns('completed_trades')}
    if 'stop_price' in cols:
        op.drop_column('completed_trades', 'stop_price')
