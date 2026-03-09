"""create trade_annotations table; migrate annotation data; drop from completed_trades

Revision ID: 2026_03_09e_trade_annotations
Revises: 2026_03_09d_all_missing
Create Date: 2026-03-09 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '2026_03_09e_trade_annotations'
down_revision: Union[str, Sequence[str], None] = '2026_03_09d_all_missing'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # 1. Drop and recreate trade_annotations if it exists with wrong schema,
    #    or create fresh if it doesn't exist.
    #    Source of truth for annotation data is still completed_trades at this point.
    if inspector.has_table('trade_annotations'):
        op.drop_table('trade_annotations')

    op.create_table(
        'trade_annotations',
        sa.Column('annotation_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('completed_trade_id', sa.BigInteger(), nullable=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('opened_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('setup_pattern_id', sa.BigInteger(), nullable=True),
        sa.Column('setup_source_id', sa.BigInteger(), nullable=True),
        sa.Column('stop_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('trade_notes', sa.Text(), nullable=True),
        sa.Column('strategy_category', sa.String(length=30), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['completed_trade_id'], ['completed_trades.completed_trade_id'],
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['setup_pattern_id'], ['setup_patterns.pattern_id']),
        sa.ForeignKeyConstraint(['setup_source_id'], ['setup_sources.source_id']),
        sa.PrimaryKeyConstraint('annotation_id'),
        sa.UniqueConstraint('user_id', 'symbol', 'opened_at', name='uq_annotation_per_trade'),
    )
    op.create_index('ix_trade_annotations_completed_trade_id', 'trade_annotations',
                    ['completed_trade_id'])

    # 2. Migrate existing annotation data from completed_trades (if columns still there)
    ct_cols = {c['name'] for c in inspector.get_columns('completed_trades')}
    annotation_cols = ['setup_pattern_id', 'setup_source_id', 'stop_price',
                       'trade_notes', 'strategy_category']
    existing_ann_cols = [c for c in annotation_cols if c in ct_cols]

    if existing_ann_cols:
        has_data_condition = ' OR '.join(f'{c} IS NOT NULL' for c in existing_ann_cols)
        select_cols = ', '.join(existing_ann_cols)
        null_cols = ', '.join(
            f'NULL AS {c}' for c in annotation_cols if c not in existing_ann_cols
        )
        all_cols = select_cols + (', ' + null_cols if null_cols else '')

        conn.execute(sa.text(f"""
            INSERT INTO trade_annotations
                (completed_trade_id, user_id, symbol, opened_at,
                 {', '.join(annotation_cols)})
            SELECT completed_trade_id, user_id, symbol, opened_at, {all_cols}
            FROM completed_trades
            WHERE opened_at IS NOT NULL
              AND ({has_data_condition})
            ON CONFLICT (user_id, symbol, opened_at) DO UPDATE
              SET completed_trade_id = EXCLUDED.completed_trade_id,
                  {', '.join(f"{c} = COALESCE(trade_annotations.{c}, EXCLUDED.{c})" for c in annotation_cols)}
        """))

    # 2b. Backfill completed_trade_id on rows that were created before the column existed
    conn.execute(sa.text("""
        UPDATE trade_annotations ta
        SET completed_trade_id = ct.completed_trade_id
        FROM completed_trades ct
        WHERE ct.user_id   = ta.user_id
          AND ct.symbol    = ta.symbol
          AND ct.opened_at = ta.opened_at
          AND ta.completed_trade_id IS NULL
    """))

    # 3. Drop annotation columns from completed_trades (idempotent)
    for fk_name in ['fk_completed_trades_setup_pattern_id', 'fk_completed_trades_setup_source_id']:
        fk_result = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_type='FOREIGN KEY' AND constraint_name=:n"
        ), {"n": fk_name})
        if fk_result.fetchone():
            op.drop_constraint(fk_name, 'completed_trades', type_='foreignkey')

    for col in annotation_cols:
        if col in ct_cols:
            op.drop_column('completed_trades', col)


def downgrade() -> None:
    conn = op.get_bind()
    ct_cols = {c['name'] for c in sa.inspect(conn).get_columns('completed_trades')}

    for col, col_def in [
        ('setup_pattern_id', sa.Column('setup_pattern_id', sa.BigInteger(), nullable=True)),
        ('setup_source_id',  sa.Column('setup_source_id',  sa.BigInteger(), nullable=True)),
        ('stop_price',       sa.Column('stop_price', sa.Numeric(18, 8), nullable=True)),
        ('trade_notes',      sa.Column('trade_notes', sa.Text(), nullable=True)),
        ('strategy_category', sa.Column('strategy_category', sa.String(30), nullable=True)),
    ]:
        if col not in ct_cols:
            op.add_column('completed_trades', col_def)

    op.create_foreign_key('fk_completed_trades_setup_pattern_id',
                          'completed_trades', 'setup_patterns',
                          ['setup_pattern_id'], ['pattern_id'])
    op.create_foreign_key('fk_completed_trades_setup_source_id',
                          'completed_trades', 'setup_sources',
                          ['setup_source_id'], ['source_id'])

    op.execute("""
        UPDATE completed_trades ct
        SET setup_pattern_id  = ta.setup_pattern_id,
            setup_source_id   = ta.setup_source_id,
            stop_price        = ta.stop_price,
            trade_notes       = ta.trade_notes,
            strategy_category = ta.strategy_category
        FROM trade_annotations ta
        WHERE ta.completed_trade_id = ct.completed_trade_id
    """)

    op.drop_index('ix_trade_annotations_completed_trade_id', 'trade_annotations')
    op.drop_table('trade_annotations')
