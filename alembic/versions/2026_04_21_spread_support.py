"""Add spread_order_tag to trades and spread_group_id to completed_trades

Revision ID: 2026_04_21_spread_support
Revises: 2026_04_08_gpa_invalid_outcome
Create Date: 2026-04-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "2026_04_21_spread_support"
down_revision: Union[str, None] = "2026_04_08_gpa_invalid_outcome"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE trades ADD COLUMN IF NOT EXISTS spread_order_tag VARCHAR(100)"
    )
    op.execute(
        "ALTER TABLE completed_trades ADD COLUMN IF NOT EXISTS spread_group_id VARCHAR(200)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS spread_order_tag")
    op.execute("ALTER TABLE completed_trades DROP COLUMN IF EXISTS spread_group_id")
