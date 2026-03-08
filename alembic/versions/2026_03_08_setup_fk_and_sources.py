"""setup_pattern_fk_and_setup_sources

Revision ID: 2026_03_08_setup_fk
Revises: c8f2a9d47b31
Create Date: 2026-03-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2026_03_08_setup_fk'
down_revision: Union[str, Sequence[str], None] = 'c8f2a9d47b31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add setup_sources table and convert setup_pattern text to FK."""

    # 1. Create setup_sources table
    op.create_table(
        'setup_sources',
        sa.Column('source_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('source_name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('TRUE')),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('source_id'),
    )

    # 2. Case-insensitive unique index on setup_sources
    op.execute(
        'CREATE UNIQUE INDEX uq_source_per_user ON setup_sources (user_id, LOWER(source_name))'
    )

    # 3. Drop existing unique constraint on setup_patterns (may not exist under that name)
    try:
        op.drop_constraint('unique_pattern_per_user', 'setup_patterns', type_='unique')
    except Exception:
        pass

    # 4. Alter setup_patterns.pattern_name VARCHAR(50) -> VARCHAR(100)
    op.alter_column(
        'setup_patterns', 'pattern_name',
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        existing_nullable=False
    )

    # 5. Drop pattern_description and pattern_category if they exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = {c['name'] for c in inspector.get_columns('setup_patterns')}
    if 'pattern_description' in existing_cols:
        op.drop_column('setup_patterns', 'pattern_description')
    if 'pattern_category' in existing_cols:
        op.drop_column('setup_patterns', 'pattern_category')

    # 6. Case-insensitive unique index on setup_patterns
    op.execute(
        'CREATE UNIQUE INDEX uq_pattern_per_user ON setup_patterns (user_id, LOWER(pattern_name))'
    )

    # 7. Add setup_pattern_id FK to completed_trades
    op.add_column(
        'completed_trades',
        sa.Column('setup_pattern_id', sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        'fk_completed_trades_setup_pattern_id',
        'completed_trades', 'setup_patterns',
        ['setup_pattern_id'], ['pattern_id']
    )

    # 8. Add setup_source_id FK to completed_trades
    op.add_column(
        'completed_trades',
        sa.Column('setup_source_id', sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        'fk_completed_trades_setup_source_id',
        'completed_trades', 'setup_sources',
        ['setup_source_id'], ['source_id']
    )

    # 9. Data migration: populate setup_patterns from existing text values,
    #    then backfill setup_pattern_id on completed_trades
    op.execute("""
        INSERT INTO setup_patterns (user_id, pattern_name, is_active, created_at, updated_at)
        SELECT DISTINCT user_id, setup_pattern, TRUE, now(), now()
        FROM completed_trades
        WHERE setup_pattern IS NOT NULL AND setup_pattern != ''
        ON CONFLICT DO NOTHING
    """)

    op.execute("""
        UPDATE completed_trades ct
        SET setup_pattern_id = sp.pattern_id
        FROM setup_patterns sp
        WHERE sp.user_id = ct.user_id
          AND LOWER(sp.pattern_name) = LOWER(ct.setup_pattern)
          AND ct.setup_pattern IS NOT NULL AND ct.setup_pattern != ''
    """)

    # 10. Drop the old setup_pattern text column
    op.drop_column('completed_trades', 'setup_pattern')


def downgrade() -> None:
    """Downgrade schema: restore setup_pattern text column, drop FKs and setup_sources."""

    # Re-add setup_pattern text column
    op.add_column(
        'completed_trades',
        sa.Column('setup_pattern', sa.Text(), nullable=True)
    )

    # Populate from join with setup_patterns
    op.execute("""
        UPDATE completed_trades ct
        SET setup_pattern = sp.pattern_name
        FROM setup_patterns sp
        WHERE sp.pattern_id = ct.setup_pattern_id
    """)

    # Drop setup_source_id FK and column
    op.drop_constraint('fk_completed_trades_setup_source_id', 'completed_trades', type_='foreignkey')
    op.drop_column('completed_trades', 'setup_source_id')

    # Drop setup_pattern_id FK and column
    op.drop_constraint('fk_completed_trades_setup_pattern_id', 'completed_trades', type_='foreignkey')
    op.drop_column('completed_trades', 'setup_pattern_id')

    # Drop functional index on setup_patterns
    op.execute('DROP INDEX IF EXISTS uq_pattern_per_user')

    # Restore unique constraint on setup_patterns
    op.create_unique_constraint('unique_pattern_per_user', 'setup_patterns', ['user_id', 'pattern_name'])

    # Restore pattern_name to VARCHAR(50)
    op.alter_column(
        'setup_patterns', 'pattern_name',
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        existing_nullable=False
    )

    # Restore dropped columns
    op.add_column('setup_patterns', sa.Column('pattern_description', sa.Text(), nullable=True))
    op.add_column('setup_patterns', sa.Column('pattern_category', sa.String(length=30), nullable=True))

    # Drop functional index on setup_sources
    op.execute('DROP INDEX IF EXISTS uq_source_per_user')

    # Drop setup_sources table
    op.drop_table('setup_sources')
