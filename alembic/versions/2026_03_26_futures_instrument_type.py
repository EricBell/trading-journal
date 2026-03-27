"""Add FUTURES to instrument_type check constraint

Revision ID: 2026_03_26_futures
Revises: 2026_03_19_journal_notes
Create Date: 2026-03-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = '2026_03_26_futures'
down_revision: Union[str, Sequence[str], None] = '2026_03_19_journal_notes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old constraint then recreate with FUTURES added
    op.drop_constraint('valid_instrument_type', 'trades', type_='check')
    op.create_check_constraint(
        'valid_instrument_type',
        'trades',
        "instrument_type IN ('EQUITY', 'OPTION', 'FUTURES')",
    )


def downgrade() -> None:
    op.drop_constraint('valid_instrument_type', 'trades', type_='check')
    op.create_check_constraint(
        'valid_instrument_type',
        'trades',
        "instrument_type IN ('EQUITY', 'OPTION')",
    )
