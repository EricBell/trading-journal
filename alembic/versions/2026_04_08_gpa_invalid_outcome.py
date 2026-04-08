"""Add 'invalid' to grail_plan_analyses outcome check constraint

Revision ID: 2026_04_08_gpa_invalid_outcome
Revises: 2026_04_07b_gpa_no_data
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "2026_04_08_gpa_invalid_outcome"
down_revision: Union[str, None] = "2026_04_07c_gpa_bars_expected"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE grail_plan_analyses DROP CONSTRAINT IF EXISTS chk_gpa_outcome")
    op.execute(
        "ALTER TABLE grail_plan_analyses ADD CONSTRAINT chk_gpa_outcome "
        "CHECK (outcome IN ('no_data', 'no_entry', 'success', 'failure', 'inconclusive', 'invalid'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE grail_plan_analyses DROP CONSTRAINT IF EXISTS chk_gpa_outcome")
    op.execute(
        "ALTER TABLE grail_plan_analyses ADD CONSTRAINT chk_gpa_outcome "
        "CHECK (outcome IN ('no_data', 'no_entry', 'success', 'failure', 'inconclusive'))"
    )
