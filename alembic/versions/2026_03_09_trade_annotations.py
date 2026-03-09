"""trade annotations stub (schema already applied)

Revision ID: 2026_03_09_trade_annotations
Revises: 2026_03_08b_stop_price
Create Date: 2026-03-09 00:00:00.000000

"""
from typing import Sequence, Union

revision: str = '2026_03_09_trade_annotations'
down_revision: Union[str, Sequence[str], None] = '2026_03_08b_stop_price'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
