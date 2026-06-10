"""Add backtest_strategy_types, backtest_underlyings, backtest_runs, backtest_leg_rules tables

Revision ID: 2026_06_04_backtest_runs
Revises: 2026_05_29_atm_options
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "2026_06_04_backtest_runs"
down_revision: Union[str, None] = "2026_05_29_atm_options"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_strategy_types (
            strategy_type_id  BIGSERIAL PRIMARY KEY,
            user_id           BIGINT NOT NULL REFERENCES users(user_id),
            strategy_name     VARCHAR(100) NOT NULL,
            is_active         BOOLEAN NOT NULL DEFAULT TRUE,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_backtest_strategy_type_per_user
        ON backtest_strategy_types (user_id, lower(strategy_name))
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_underlyings (
            underlying_id   BIGSERIAL PRIMARY KEY,
            user_id         BIGINT NOT NULL REFERENCES users(user_id),
            underlying_name VARCHAR(50) NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_backtest_underlying_per_user
        ON backtest_underlyings (user_id, lower(underlying_name))
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            run_id              BIGSERIAL PRIMARY KEY,
            user_id             BIGINT NOT NULL REFERENCES users(user_id),
            strategy_type_id    BIGINT REFERENCES backtest_strategy_types(strategy_type_id),
            underlying_id       BIGINT REFERENCES backtest_underlyings(underlying_id),
            entry_time          VARCHAR(10),
            entry_style         VARCHAR(20) NOT NULL DEFAULT 'simultaneous'
                                    CONSTRAINT chk_backtest_run_entry_style
                                    CHECK (entry_style IN ('simultaneous', 'staged')),
            spread_width_pts    INTEGER,
            dte_at_entry        INTEGER,
            strike_selection    VARCHAR(200),
            profit_target_pct   NUMERIC(5,2),
            stop_loss_rule      VARCHAR(200),
            date_range_start    DATE,
            date_range_end      DATE,
            backtest_tool       VARCHAR(100),
            notes               TEXT,
            status              VARCHAR(20) NOT NULL DEFAULT 'draft'
                                    CONSTRAINT chk_backtest_run_status
                                    CHECK (status IN ('draft', 'complete')),
            trade_count         INTEGER,
            win_rate_pct        NUMERIC(5,2),
            avg_pnl_per_trade   NUMERIC(12,2),
            total_pnl           NUMERIC(12,2),
            avg_win             NUMERIC(12,2),
            avg_loss            NUMERIC(12,2),
            profit_factor       NUMERIC(8,4),
            max_win             NUMERIC(12,2),
            max_loss            NUMERIC(12,2),
            max_drawdown        NUMERIC(12,2),
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_leg_rules (
            rule_id           BIGSERIAL PRIMARY KEY,
            run_id            BIGINT NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
            user_id           BIGINT NOT NULL REFERENCES users(user_id),
            leg_target        VARCHAR(100) NOT NULL,
            trigger_condition VARCHAR(200) NOT NULL,
            action            VARCHAR(100) NOT NULL,
            sort_order        INTEGER NOT NULL DEFAULT 0,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            updated_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_backtest_leg_rules_run_id ON backtest_leg_rules (run_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backtest_leg_rules")
    op.execute("DROP TABLE IF EXISTS backtest_runs")
    op.execute("DROP INDEX IF EXISTS uq_backtest_underlying_per_user")
    op.execute("DROP TABLE IF EXISTS backtest_underlyings")
    op.execute("DROP INDEX IF EXISTS uq_backtest_strategy_type_per_user")
    op.execute("DROP TABLE IF EXISTS backtest_strategy_types")
