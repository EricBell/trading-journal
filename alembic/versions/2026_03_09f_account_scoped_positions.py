"""Scope positions unique constraint to include account_id

Revision ID: 2026_03_09f_account_scoped_positions
Revises: 2026_03_09e_trade_annotations
Create Date: 2026-03-09 18:00:00.000000

Adds account_id to the positions unique constraint so that fills from different
brokerage accounts for the same symbol produce separate position rows rather than
being merged into one.

Before: UNIQUE(user_id, symbol, instrument_type, option_details)
After:  UNIQUE(user_id, symbol, instrument_type, option_details, account_id)

Note: because account_id is nullable and PostgreSQL treats NULLs as distinct in
unique indexes, correctness for null-account positions continues to be enforced
by the PositionTracker delete-then-rebuild logic, not by the constraint alone.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2026_03_09f_acct_positions'
down_revision: Union[str, Sequence[str], None] = '2026_03_09e_trade_annotations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('unique_position_per_user', 'positions', type_='unique')
    op.create_unique_constraint(
        'unique_position_per_user',
        'positions',
        ['user_id', 'symbol', 'instrument_type', 'option_details', 'account_id'],
    )


def downgrade() -> None:
    op.drop_constraint('unique_position_per_user', 'positions', type_='unique')
    op.create_unique_constraint(
        'unique_position_per_user',
        'positions',
        ['user_id', 'symbol', 'instrument_type', 'option_details'],
    )
