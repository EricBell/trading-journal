"""add stop_price to completed_trades

Revision ID: 2026_03_08b_stop_price
Revises: 2026_03_08_setup_fk
Create Date: 2026-03-08 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '2026_03_08b_stop_price'
down_revision: Union[str, Sequence[str], None] = '2026_03_08_setup_fk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'completed_trades',
        sa.Column('stop_price', sa.Numeric(18, 8), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('completed_trades', 'stop_price')
