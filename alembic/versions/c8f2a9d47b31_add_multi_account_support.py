"""add_multi_account_support

Revision ID: c8f2a9d47b31
Revises: 5ecc33ba8812
Create Date: 2026-03-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c8f2a9d47b31'
down_revision: Union[str, Sequence[str], None] = '5ecc33ba8812'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'accounts',
        sa.Column('account_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('account_number', sa.String(length=50), nullable=False),
        sa.Column('account_name', sa.String(length=100), nullable=True),
        sa.Column('account_type', sa.String(length=50), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('account_id'),
        sa.UniqueConstraint('user_id', 'account_number', name='unique_account_per_user'),
    )

    op.add_column('trades', sa.Column('account_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'fk_trades_account_id', 'trades', 'accounts', ['account_id'], ['account_id']
    )

    op.add_column('completed_trades', sa.Column('account_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'fk_completed_trades_account_id', 'completed_trades', 'accounts', ['account_id'], ['account_id']
    )

    op.add_column('positions', sa.Column('account_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'fk_positions_account_id', 'positions', 'accounts', ['account_id'], ['account_id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_positions_account_id', 'positions', type_='foreignkey')
    op.drop_column('positions', 'account_id')

    op.drop_constraint('fk_completed_trades_account_id', 'completed_trades', type_='foreignkey')
    op.drop_column('completed_trades', 'account_id')

    op.drop_constraint('fk_trades_account_id', 'trades', type_='foreignkey')
    op.drop_column('trades', 'account_id')

    op.drop_table('accounts')
