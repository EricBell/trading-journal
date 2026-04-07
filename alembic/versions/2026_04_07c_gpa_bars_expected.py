"""Add bars_expected to grail_plan_analyses

Revision ID: 2026_04_07c_gpa_bars_expected
Revises: 2026_04_07b_gpa_no_data
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2026_04_07c_gpa_bars_expected"
down_revision: Union[str, None] = "2026_04_07b_gpa_no_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("grail_plan_analyses")]
    if "bars_expected" not in cols:
        op.add_column(
            "grail_plan_analyses",
            sa.Column("bars_expected", sa.Integer, nullable=True),
        )


def downgrade() -> None:
    op.drop_column("grail_plan_analyses", "bars_expected")
