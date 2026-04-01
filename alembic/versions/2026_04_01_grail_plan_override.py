"""Add grail_plan_id and grail_plan_rejected to trade_annotations

Revision ID: 2026_04_01_grail_plan_override
Revises: 2026_03_29_hg_analysis
Create Date: 2026-04-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2026_04_01_grail_plan_override"
down_revision: Union[str, None] = "2026_03_29_hg_analysis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("trade_annotations")}

    if "grail_plan_id" not in existing_cols:
        op.add_column(
            "trade_annotations",
            sa.Column("grail_plan_id", sa.Integer(), nullable=True),
        )

    if "grail_plan_rejected" not in existing_cols:
        op.add_column(
            "trade_annotations",
            sa.Column(
                "grail_plan_rejected",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c["name"] for c in inspector.get_columns("trade_annotations")}

    if "grail_plan_rejected" in existing_cols:
        op.drop_column("trade_annotations", "grail_plan_rejected")

    if "grail_plan_id" in existing_cols:
        op.drop_column("trade_annotations", "grail_plan_id")
