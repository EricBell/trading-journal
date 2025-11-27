"""add_multi_user_support

Revision ID: 5ecc33ba8812
Revises: d5dd60a8f5ae
Create Date: 2025-11-27 12:45:04.918002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5ecc33ba8812'
down_revision: Union[str, Sequence[str], None] = 'd5dd60a8f5ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Create users table
    op.create_table('users',
    sa.Column('user_id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('auth_method', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('api_key_hash', sa.String(length=64), nullable=True),
    sa.Column('api_key_created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('last_login_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.CheckConstraint("auth_method IN ('api_key', 'jwt', 'oauth', 'session')", name='valid_auth_method'),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('api_key_hash'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('username')
    )

    # Step 2: Create system user for existing data
    op.execute("""
        INSERT INTO users (username, email, auth_method, is_active, is_admin, created_at, updated_at)
        VALUES ('system', 'system@trading-journal.local', 'api_key', true, true, NOW(), NOW())
    """)

    # Step 3: Add user_id columns as nullable first
    op.add_column('trades', sa.Column('user_id', sa.BigInteger(), nullable=True))
    op.add_column('completed_trades', sa.Column('user_id', sa.BigInteger(), nullable=True))
    op.add_column('positions', sa.Column('user_id', sa.BigInteger(), nullable=True))
    op.add_column('setup_patterns', sa.Column('user_id', sa.BigInteger(), nullable=True))
    op.add_column('processing_log', sa.Column('user_id', sa.BigInteger(), nullable=True))

    # Step 4: Populate existing data with system user's ID
    op.execute("""
        UPDATE trades SET user_id = (SELECT user_id FROM users WHERE username = 'system')
        WHERE user_id IS NULL
    """)
    op.execute("""
        UPDATE completed_trades SET user_id = (SELECT user_id FROM users WHERE username = 'system')
        WHERE user_id IS NULL
    """)
    op.execute("""
        UPDATE positions SET user_id = (SELECT user_id FROM users WHERE username = 'system')
        WHERE user_id IS NULL
    """)
    op.execute("""
        UPDATE setup_patterns SET user_id = (SELECT user_id FROM users WHERE username = 'system')
        WHERE user_id IS NULL
    """)
    op.execute("""
        UPDATE processing_log SET user_id = (SELECT user_id FROM users WHERE username = 'system')
        WHERE user_id IS NULL
    """)

    # Step 5: Make user_id columns non-nullable
    op.alter_column('trades', 'user_id', nullable=False)
    op.alter_column('completed_trades', 'user_id', nullable=False)
    op.alter_column('positions', 'user_id', nullable=False)
    op.alter_column('setup_patterns', 'user_id', nullable=False)
    op.alter_column('processing_log', 'user_id', nullable=False)

    # Step 6: Create foreign keys
    op.create_foreign_key('fk_trades_user_id', 'trades', 'users', ['user_id'], ['user_id'])
    op.create_foreign_key('fk_completed_trades_user_id', 'completed_trades', 'users', ['user_id'], ['user_id'])
    op.create_foreign_key('fk_positions_user_id', 'positions', 'users', ['user_id'], ['user_id'])
    op.create_foreign_key('fk_setup_patterns_user_id', 'setup_patterns', 'users', ['user_id'], ['user_id'])
    op.create_foreign_key('fk_processing_log_user_id', 'processing_log', 'users', ['user_id'], ['user_id'])

    # Step 7: Update unique constraints
    op.drop_constraint('trades_unique_key_key', 'trades', type_='unique')
    op.create_unique_constraint('unique_trade_per_user', 'trades', ['user_id', 'unique_key'])

    op.drop_constraint('unique_position', 'positions', type_='unique')
    op.create_unique_constraint('unique_position_per_user', 'positions', ['user_id', 'symbol', 'instrument_type', 'option_details'])

    op.drop_constraint('unique_processing_attempt', 'processing_log', type_='unique')
    op.create_unique_constraint('unique_processing_attempt_per_user', 'processing_log', ['user_id', 'file_path', 'processing_started_at'])

    op.create_unique_constraint('unique_pattern_per_user', 'setup_patterns', ['user_id', 'pattern_name'])

    # Step 8: Create indexes for performance
    op.create_index('idx_trades_user_id', 'trades', ['user_id'])
    op.create_index('idx_completed_trades_user_id', 'completed_trades', ['user_id'])
    op.create_index('idx_positions_user_id', 'positions', ['user_id'])
    op.create_index('idx_setup_patterns_user_id', 'setup_patterns', ['user_id'])
    op.create_index('idx_processing_log_user_id', 'processing_log', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Step 1: Drop indexes
    op.drop_index('idx_processing_log_user_id', 'processing_log')
    op.drop_index('idx_setup_patterns_user_id', 'setup_patterns')
    op.drop_index('idx_positions_user_id', 'positions')
    op.drop_index('idx_completed_trades_user_id', 'completed_trades')
    op.drop_index('idx_trades_user_id', 'trades')

    # Step 2: Restore old unique constraints, drop new ones
    op.drop_constraint('unique_pattern_per_user', 'setup_patterns', type_='unique')

    op.drop_constraint('unique_processing_attempt_per_user', 'processing_log', type_='unique')
    op.create_unique_constraint('unique_processing_attempt', 'processing_log', ['file_path', 'processing_started_at'])

    op.drop_constraint('unique_position_per_user', 'positions', type_='unique')
    op.create_unique_constraint('unique_position', 'positions', ['symbol', 'instrument_type', 'option_details'])

    op.drop_constraint('unique_trade_per_user', 'trades', type_='unique')
    op.create_unique_constraint('trades_unique_key_key', 'trades', ['unique_key'])

    # Step 3: Drop foreign keys
    op.drop_constraint('fk_processing_log_user_id', 'processing_log', type_='foreignkey')
    op.drop_constraint('fk_setup_patterns_user_id', 'setup_patterns', type_='foreignkey')
    op.drop_constraint('fk_positions_user_id', 'positions', type_='foreignkey')
    op.drop_constraint('fk_completed_trades_user_id', 'completed_trades', type_='foreignkey')
    op.drop_constraint('fk_trades_user_id', 'trades', type_='foreignkey')

    # Step 4: Drop user_id columns
    op.drop_column('processing_log', 'user_id')
    op.drop_column('setup_patterns', 'user_id')
    op.drop_column('positions', 'user_id')
    op.drop_column('completed_trades', 'user_id')
    op.drop_column('trades', 'user_id')

    # Step 5: Drop users table
    op.drop_table('users')
