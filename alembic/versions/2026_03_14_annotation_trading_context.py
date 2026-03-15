"""Add atm_engaged, exit_reason, underlying_at_entry to trade_annotations

Revision ID: 2026_03_14_annotation_trading_context
Revises: 2026_03_09_trade_annotations
Create Date: 2026-03-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '2026_03_14_ann_ctx'
down_revision: Union[str, Sequence[str], None] = '2026_03_09f_acct_positions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trade_annotations',
        sa.Column('atm_engaged', sa.String(20), nullable=True))
    op.add_column('trade_annotations',
        sa.Column('exit_reason', sa.String(30), nullable=True))
    op.add_column('trade_annotations',
        sa.Column('underlying_at_entry', sa.Numeric(18, 8), nullable=True))


def downgrade() -> None:
    op.drop_column('trade_annotations', 'underlying_at_entry')
    op.drop_column('trade_annotations', 'exit_reason')
    op.drop_column('trade_annotations', 'atm_engaged')
