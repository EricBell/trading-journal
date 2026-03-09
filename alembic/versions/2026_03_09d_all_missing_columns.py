"""add all missing columns to completed_trades

Revision ID: 2026_03_09d_all_missing
Revises: 2026_03_09c_stop_price
Create Date: 2026-03-09 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '2026_03_09d_all_missing'
down_revision: Union[str, Sequence[str], None] = '2026_03_09c_stop_price'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(conn, table):
    return {c['name'] for c in sa.inspect(conn).get_columns(table)}


def _add_if_missing(conn, table, col_name, col_def):
    if col_name not in _cols(conn, table):
        op.add_column(table, col_def)


def upgrade() -> None:
    conn = op.get_bind()

    _add_if_missing(conn, 'completed_trades', 'trade_notes',
        sa.Column('trade_notes', sa.Text(), nullable=True))

    _add_if_missing(conn, 'completed_trades', 'gross_proceeds',
        sa.Column('gross_proceeds', sa.Numeric(18, 8), nullable=True))

    _add_if_missing(conn, 'completed_trades', 'gross_cost',
        sa.Column('gross_cost', sa.Numeric(18, 8), nullable=True))

    _add_if_missing(conn, 'completed_trades', 'hold_duration',
        sa.Column('hold_duration', sa.Interval(), nullable=True))

    _add_if_missing(conn, 'completed_trades', 'option_details',
        sa.Column('option_details', postgresql.JSONB(), nullable=True))

    _add_if_missing(conn, 'completed_trades', 'account_id',
        sa.Column('account_id', sa.BigInteger(), sa.ForeignKey('accounts.account_id'), nullable=True))


def downgrade() -> None:
    pass
