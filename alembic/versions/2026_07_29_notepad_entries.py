"""Add notepad_entries table (issue #33 — pre- and post-trade notepad)

Revision ID: 2026_07_29_notepad_entries
Revises: 2026_06_04_backtest_runs
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "2026_07_29_notepad_entries"
down_revision: Union[str, None] = "2026_06_04_backtest_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS notepad_entries (
            notepad_id         BIGSERIAL PRIMARY KEY,
            user_id            BIGINT NOT NULL REFERENCES users(user_id),
            symbol             VARCHAR(50),
            account_id         BIGINT REFERENCES accounts(account_id),
            body               TEXT NOT NULL,
            created_at         TIMESTAMPTZ DEFAULT NOW(),
            updated_at         TIMESTAMPTZ DEFAULT NOW(),
            matched_trade_id   BIGINT REFERENCES completed_trades(completed_trade_id) ON DELETE SET NULL,
            matched_symbol     VARCHAR(50),
            matched_opened_at  TIMESTAMPTZ,
            matched_at         TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_notepad_entries_user_id ON notepad_entries (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_notepad_entries_matched_trade_id ON notepad_entries (matched_trade_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notepad_entries_matched_trade_id")
    op.execute("DROP INDEX IF EXISTS ix_notepad_entries_user_id")
    op.execute("DROP TABLE IF EXISTS notepad_entries")
