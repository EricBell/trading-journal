"""fix missing schema from 2026_03_09_trade_annotations

Adds setup_sources table, setup_pattern_id/setup_source_id FKs, and
strategy_category to completed_trades — only if not already present.

Revision ID: 2026_03_09b_fix_schema
Revises: 2026_03_09_trade_annotations
Create Date: 2026-03-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '2026_03_09b_fix_schema'
down_revision: Union[str, Sequence[str], None] = '2026_03_09_trade_annotations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table_name: str) -> bool:
    return sa.inspect(conn).has_table(table_name)


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    cols = {c['name'] for c in sa.inspect(conn).get_columns(table_name)}
    return column_name in cols


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": index_name}
    )
    return result.fetchone() is not None


def _fk_exists(conn, constraint_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_type='FOREIGN KEY' AND constraint_name=:n"
        ),
        {"n": constraint_name}
    )
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create setup_sources table if missing
    if not _table_exists(conn, 'setup_sources'):
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

    if not _index_exists(conn, 'uq_source_per_user'):
        op.execute(
            'CREATE UNIQUE INDEX uq_source_per_user ON setup_sources (user_id, LOWER(source_name))'
        )

    # 2. Ensure setup_patterns has the case-insensitive unique index
    if not _index_exists(conn, 'uq_pattern_per_user'):
        # Drop old constraint if it exists under either name
        try:
            op.drop_constraint('unique_pattern_per_user', 'setup_patterns', type_='unique')
        except Exception:
            pass
        op.execute(
            'CREATE UNIQUE INDEX uq_pattern_per_user ON setup_patterns (user_id, LOWER(pattern_name))'
        )

    # 3. Add setup_pattern_id FK to completed_trades
    if not _column_exists(conn, 'completed_trades', 'setup_pattern_id'):
        op.add_column(
            'completed_trades',
            sa.Column('setup_pattern_id', sa.BigInteger(), nullable=True)
        )
        # Backfill from legacy text column if it still exists
        if _column_exists(conn, 'completed_trades', 'setup_pattern'):
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

        if not _fk_exists(conn, 'fk_completed_trades_setup_pattern_id'):
            op.create_foreign_key(
                'fk_completed_trades_setup_pattern_id',
                'completed_trades', 'setup_patterns',
                ['setup_pattern_id'], ['pattern_id']
            )

    # 4. Add setup_source_id FK to completed_trades
    if not _column_exists(conn, 'completed_trades', 'setup_source_id'):
        op.add_column(
            'completed_trades',
            sa.Column('setup_source_id', sa.BigInteger(), nullable=True)
        )
        if not _fk_exists(conn, 'fk_completed_trades_setup_source_id'):
            op.create_foreign_key(
                'fk_completed_trades_setup_source_id',
                'completed_trades', 'setup_sources',
                ['setup_source_id'], ['source_id']
            )

    # 5. Add strategy_category to completed_trades
    if not _column_exists(conn, 'completed_trades', 'strategy_category'):
        op.add_column(
            'completed_trades',
            sa.Column('strategy_category', sa.String(length=30), nullable=True)
        )

    # 6. Drop legacy setup_pattern text column if it still exists
    if _column_exists(conn, 'completed_trades', 'setup_pattern'):
        op.drop_column('completed_trades', 'setup_pattern')


def downgrade() -> None:
    conn = op.get_bind()

    # Restore setup_pattern text column
    if not _column_exists(conn, 'completed_trades', 'setup_pattern'):
        op.add_column('completed_trades', sa.Column('setup_pattern', sa.Text(), nullable=True))
        op.execute("""
            UPDATE completed_trades ct
            SET setup_pattern = sp.pattern_name
            FROM setup_patterns sp
            WHERE sp.pattern_id = ct.setup_pattern_id
        """)

    if _column_exists(conn, 'completed_trades', 'strategy_category'):
        op.drop_column('completed_trades', 'strategy_category')

    if _fk_exists(conn, 'fk_completed_trades_setup_source_id'):
        op.drop_constraint('fk_completed_trades_setup_source_id', 'completed_trades', type_='foreignkey')
    if _column_exists(conn, 'completed_trades', 'setup_source_id'):
        op.drop_column('completed_trades', 'setup_source_id')

    if _fk_exists(conn, 'fk_completed_trades_setup_pattern_id'):
        op.drop_constraint('fk_completed_trades_setup_pattern_id', 'completed_trades', type_='foreignkey')
    if _column_exists(conn, 'completed_trades', 'setup_pattern_id'):
        op.drop_column('completed_trades', 'setup_pattern_id')
