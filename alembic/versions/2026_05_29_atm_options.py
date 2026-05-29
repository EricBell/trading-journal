"""Add atm_options table and migrate atm_engaged to FK

Revision ID: 2026_05_29_atm_options
Revises: 2026_04_21_spread_support
Create Date: 2026-05-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "2026_05_29_atm_options"
down_revision: Union[str, None] = "2026_04_21_spread_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Maps legacy atm_engaged string values → human-readable option names
_ATM_VALUE_MAP = {
    "not_used": "Not used (manual trade)",
    "entry_only": "Entry signal only",
    "full_session": "Full session",
}


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create atm_options table
    op.execute("""
        CREATE TABLE IF NOT EXISTS atm_options (
            option_id   BIGSERIAL PRIMARY KEY,
            user_id     BIGINT NOT NULL REFERENCES users(user_id),
            option_name VARCHAR(100) NOT NULL,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_atm_option_per_user
        ON atm_options (user_id, lower(option_name))
    """)

    # 2. Add atm_option_id FK column to trade_annotations
    op.execute("""
        ALTER TABLE trade_annotations
        ADD COLUMN IF NOT EXISTS atm_option_id BIGINT
        REFERENCES atm_options(option_id) ON DELETE SET NULL
    """)

    # 3. Migrate existing atm_engaged string values to atm_options rows
    users = conn.execute(text("SELECT user_id FROM users")).fetchall()
    for (user_id,) in users:
        existing_values = conn.execute(
            text(
                "SELECT DISTINCT atm_engaged FROM trade_annotations "
                "WHERE user_id = :uid AND atm_engaged IS NOT NULL"
            ),
            {"uid": user_id},
        ).fetchall()

        for (raw_value,) in existing_values:
            display_name = _ATM_VALUE_MAP.get(raw_value, raw_value)

            # Upsert the option row
            result = conn.execute(
                text(
                    "INSERT INTO atm_options (user_id, option_name) "
                    "VALUES (:uid, :name) "
                    "ON CONFLICT (user_id, lower(option_name)) DO UPDATE "
                    "SET option_name = EXCLUDED.option_name "
                    "RETURNING option_id"
                ),
                {"uid": user_id, "name": display_name},
            )
            option_id = result.fetchone()[0]

            # Update annotations to use the new FK
            conn.execute(
                text(
                    "UPDATE trade_annotations "
                    "SET atm_option_id = :oid "
                    "WHERE user_id = :uid AND atm_engaged = :raw"
                ),
                {"oid": option_id, "uid": user_id, "raw": raw_value},
            )


def downgrade() -> None:
    op.execute("ALTER TABLE trade_annotations DROP COLUMN IF EXISTS atm_option_id")
    op.execute("DROP INDEX IF EXISTS uq_atm_option_per_user")
    op.execute("DROP TABLE IF EXISTS atm_options")
