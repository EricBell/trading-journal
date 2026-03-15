"""Add timezone column to users table

Revision ID: 2026_03_15_user_tz
Revises: 2026_03_15_ohlcv_uc
Create Date: 2026-03-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '2026_03_15_user_tz'
down_revision: Union[str, Sequence[str], None] = '2026_03_15_ohlcv_uc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c['name'] for c in inspector.get_columns('users')}
    if 'timezone' not in cols:
        op.add_column('users',
            sa.Column('timezone', sa.String(50), nullable=True, server_default='US/Eastern'))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c['name'] for c in inspector.get_columns('users')}
    if 'timezone' in cols:
        op.drop_column('users', 'timezone')
