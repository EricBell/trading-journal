"""Add journal_notes table

Revision ID: 2026_03_19_journal_notes
Revises: 2026_03_15_user_tz
Create Date: 2026-03-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '2026_03_19_journal_notes'
down_revision: Union[str, Sequence[str], None] = '2026_03_15_user_tz'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()
    if 'journal_notes' not in existing_tables:
        op.create_table(
            'journal_notes',
            sa.Column('note_id', sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.BigInteger, sa.ForeignKey('users.user_id'), nullable=False),
            sa.Column('title', sa.String(200), nullable=True),
            sa.Column('body', sa.Text, nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()
    if 'journal_notes' in existing_tables:
        op.drop_table('journal_notes')
