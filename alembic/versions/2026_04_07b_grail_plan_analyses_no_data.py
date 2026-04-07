"""Add no_data to grail_plan_analyses outcome check constraint

Revision ID: 2026_04_07b_grail_plan_analyses_no_data
Revises: 2026_04_07_grail_plan_analyses
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2026_04_07b_gpa_no_data"
down_revision: Union[str, None] = "2026_04_07_grail_plan_analyses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE grail_plan_analyses DROP CONSTRAINT IF EXISTS chk_gpa_outcome")
    op.execute(
        "ALTER TABLE grail_plan_analyses ADD CONSTRAINT chk_gpa_outcome "
        "CHECK (outcome IN ('no_data', 'no_entry', 'success', 'failure', 'inconclusive'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE grail_plan_analyses DROP CONSTRAINT IF EXISTS chk_gpa_outcome")
    op.execute(
        "ALTER TABLE grail_plan_analyses ADD CONSTRAINT chk_gpa_outcome "
        "CHECK (outcome IN ('no_entry', 'success', 'failure', 'inconclusive'))"
    )
